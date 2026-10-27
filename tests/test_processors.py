import json

from app.config import Settings
from app.db import postgres_session, timescale_session
from app.models import AisReport, Asset, Detection, SignalSample, TriageEvent
from app.processors import JobContext, dispatch
from app.processors.watchpoint import watchpoint_inference_request
from app.storage import MemoryStore
from sqlalchemy import func, select


class FakeChariot:
    def __init__(self) -> None:
        self.detect_calls = []
        self.inference_requests = []

    def detect(self, model_id, image_bytes, suffix=".bin"):
        self.detect_calls.append(model_id)
        return {
            "inference_id": "inf-1",
            "inference": {
                "detection_labels": ["vehicle"],
                "detection_scores": [0.91],
                "detection_boxes": [[1, 2, 3, 4]],
            },
        }

    def describe_image(self, model_id, image_bytes, prompt, suffix=".bin"):
        return "Two vehicles beside a pier."

    def list_triage_events(self, project_id, watchpoint_id, time_start, time_end):
        return [
            {
                "watchpoint_id": watchpoint_id,
                "chariot_event_id": "event-1",
                "review_status": "not_reviewed",
                "captured_at": None,
                "chariot_ids": {"chariot_request": "req-1"},
                "details": {},
            }
        ]

    def list_watchpoint_detections(self, watchpoint_id, time_start, time_end):
        return [
            {
                "label": "ship",
                "score": 0.7,
                "geometry": {"bbox": [1, 1, 2, 2]},
                "latitude": 21.3,
                "longitude": -157.8,
                "chariot_inference_id": "inf-w",
                "model_id": "model-w",
                "observed_at": None,
                "attributes": {"triage_event": "event-1"},
                "triage_event_external_id": "event-1",
            }
        ]

    def watchbox_model_id(self, watchpoint_id):
        return "model-w"

    def filter_inferences(self, model_id, request):
        self.inference_requests.append((model_id, request))
        return [
            {
                "label": "ship",
                "score": 0.66,
                "geometry": {"xmin": 0, "ymin": 0, "xmax": 4, "ymax": 4},
                "chariot_inference_id": "inf-store",
                "model_id": model_id,
                "latitude": 21.31,
                "longitude": -157.81,
                "observed_at": None,
                "attributes": {},
            }
        ]


def _settings(**overrides) -> Settings:
    base = dict(
        postgres_url="postgresql+psycopg://fusion:fusion@localhost:5432/fusion",
        timescale_url="postgresql+psycopg://fusion:fusion@localhost:5433/fusion",
        minio_bucket="fusion",
        chariot_detection_model_id="",
        chariot_vlm_model_id="",
        chariot_workflow_id="",
    )
    base.update(overrides)
    return Settings(**base)


def test_imagery_persists_asset_and_detections(databases):
    store = MemoryStore()
    store.put("inbox/one", b"image-bytes", "image/png")
    chariot = FakeChariot()
    with postgres_session(databases) as session, timescale_session(databases) as timescale:
        dispatch(
            "process_imagery",
            JobContext(
                session=session,
                timescale=timescale,
                store=store,
                chariot=chariot,
                settings=_settings(chariot_detection_model_id="detector-1"),
                payload={
                    "inbox_key": "inbox/one",
                    "filename": "scene.png",
                    "content_type": "image/png",
                    "modality": "eo",
                    "metadata": {"sensor": "example"},
                    "captured_at": "2026-03-01T12:00:00Z",
                    "latitude": 21.3,
                    "longitude": -157.8,
                },
            ),
        )
        assets = list(session.scalars(select(Asset)))
        detections = list(session.scalars(select(Detection)))
    assert len(assets) == 1
    assert assets[0].details["sensor"] == "example"
    assert assets[0].object_key.endswith(".png")
    assert store.get(assets[0].object_key) == b"image-bytes"
    assert "inbox/one" not in store.objects
    assert detections[0].label == "vehicle"
    assert detections[0].model_id == "detector-1"
    assert chariot.detect_calls == ["detector-1"]
    assert assets[0].details["visual_description_status"] == "not_configured"


def test_imagery_keeps_asset_when_detection_model_is_unset(databases):
    store = MemoryStore()
    store.put("inbox/two", b"image-bytes", "image/jpeg")
    with postgres_session(databases) as session, timescale_session(databases) as timescale:
        try:
            dispatch(
                "process_imagery",
                JobContext(
                    session=session,
                    timescale=timescale,
                    store=store,
                    chariot=FakeChariot(),
                    settings=_settings(),
                    payload={
                        "inbox_key": "inbox/two",
                        "filename": "scene.jpg",
                        "content_type": "image/jpeg",
                        "modality": "sar",
                        "metadata": {"pass": "desc"},
                        "latitude": 1,
                        "longitude": 2,
                    },
                ),
            )
        except RuntimeError as exc:
            assert "CHARIOT_DETECTION_MODEL_ID" in str(exc)
        else:
            raise AssertionError("expected missing model id to fail the job")
        assets = list(session.scalars(select(Asset)))
    assert len(assets) == 1
    assert assets[0].modality == "sar"
    assert assets[0].details["pass"] == "desc"


def test_watchpoint_sync_stores_events_and_inference_rows(databases):
    chariot = FakeChariot()
    with postgres_session(databases) as session, timescale_session(databases) as timescale:
        result = dispatch(
            "sync_watchpoint",
            JobContext(
                session=session,
                timescale=timescale,
                store=MemoryStore(),
                chariot=chariot,
                settings=_settings(),
                payload={
                    "watchpoint_id": "wp-1",
                    "project_id": "project-1",
                    "time_start": "2026-03-01T00:00:00Z",
                    "time_end": "2026-03-02T00:00:00Z",
                },
            ),
        )
        events = list(session.scalars(select(TriageEvent)))
        detections = list(session.scalars(select(Detection)))
    assert len(events) == 1
    assert events[0].watchpoint_id == "wp-1"
    assert {row.label for row in detections} == {"ship"}
    assert len(detections) == 2
    linked = [row for row in detections if row.triage_event_id == events[0].id]
    assert len(linked) == 1
    model_id, request = chariot.inference_requests[0]
    assert model_id == "model-w"
    assert request["filters"]["metadata_filter"][0]["key"] == "watchpoint_id"
    assert request["filters"]["metadata_filter"][0]["value"] == "wp-1"
    assert set(result["evidence"]["detection_ids"]) == {str(row.id) for row in detections}


def test_watchpoint_inference_request_shape():
    request = watchpoint_inference_request(
        {"time_start": "2026-03-01T00:00:00Z", "time_end": "2026-03-02T00:00:00Z"},
        "wp-1",
    )
    assert request["filters"]["metadata_filter"][0]["value"] == "wp-1"
    assert request["filters"]["time_window_filter"]["start"] == "2026-03-01T00:00:00Z"


def test_fmv_pull_uses_feed_filter(databases):
    chariot = FakeChariot()
    with postgres_session(databases) as session, timescale_session(databases) as timescale:
        dispatch(
            "sync_fmv",
            JobContext(
                session=session,
                timescale=timescale,
                store=MemoryStore(),
                chariot=chariot,
                settings=_settings(),
                payload={
                    "model_id": "fmv-model",
                    "feed_id": "feed-7",
                    "time_start": "2026-03-01T00:00:00Z",
                    "time_end": "2026-03-01T01:00:00Z",
                },
            ),
        )
        count = session.scalar(select(func.count()).select_from(Detection))
    assert count == 1
    assert chariot.inference_requests[0][1]["filters"]["metadata_filter"][0]["key"] == "feed_id"
    assert chariot.inference_requests[0][1]["filters"]["metadata_filter"][0]["value"] == "feed-7"


def test_timeseries_samples_land_in_timescale(databases):
    with postgres_session(databases) as session, timescale_session(databases) as timescale:
        result = dispatch(
            "ingest_timeseries",
            JobContext(
                session=session,
                timescale=timescale,
                store=MemoryStore(),
                chariot=FakeChariot(),
                settings=_settings(),
                payload={
                    "modality": "elint",
                    "source_id": "elint-1",
                    "samples": [
                        {"time": "2026-03-01T12:00:00Z", "value": 3.5, "channel": "band-a"}
                    ],
                },
            ),
        )
        rows = list(timescale.scalars(select(SignalSample)))
    assert result["evidence"]["signal_source_ids"] == ["elint-1"]
    assert rows[0].modality == "elint"
    assert rows[0].value == 3.5


NORDIC = {
    "mmsi": 211234560,
    "vessel_name": "NORDIC MARINER",
    "call_sign": "DJ7B2",
    "imo": 9432105,
    "vessel_type": 70,
    "vessel_type_cargo": "Cargo - All ships of this type",
    "length": 185,
    "width": 28,
    "draft": 8.5,
    "timestamp": "2026-10-15T09:42:15Z",
    "latitude": 53.5412,
    "longitude": 9.9124,
    "speed_over_ground_knots": 12.4,
    "course_over_ground_degrees": 264.5,
    "heading_degrees": 266,
    "navigational_status_code": 0,
    "navigational_status": "Underway using engine",
    "destination": "HAMBURG",
    "eta": "10-15 11:30",
}


def test_ais_report_lands_in_postgres(databases):
    from app.ais import reports_from_body

    with postgres_session(databases) as session, timescale_session(databases) as timescale:
        result = dispatch(
            "ingest_ais",
            JobContext(
                session=session,
                timescale=timescale,
                store=MemoryStore(),
                chariot=FakeChariot(),
                settings=_settings(),
                payload={"reports": reports_from_body(NORDIC)},
            ),
        )
        row = session.scalars(select(AisReport)).one()
    assert result["evidence"]["sample_mmsis"] == ["211234560"]
    assert result["evidence"]["sample_vessel_names"] == ["NORDIC MARINER"]
    assert result["evidence"]["sample_destinations"] == ["HAMBURG"]
    assert row.mmsi == "211234560"
    assert row.imo == "9432105"
    assert row.vessel_type == 70
    assert row.navigational_status_code == 0
    assert row.speed_over_ground_knots == 12.4
    assert row.heading_degrees == 266
    assert row.destination == "HAMBURG"
    assert row.eta == "10-15 11:30"
    assert row.latitude == 53.5412


def test_staged_ais_file_is_loaded_and_removed(databases):
    store = MemoryStore()
    store.put("inbox/ais", json.dumps([NORDIC]).encode(), "application/json")
    with postgres_session(databases) as session, timescale_session(databases) as timescale:
        result = dispatch(
            "ingest_ais",
            JobContext(
                session=session,
                timescale=timescale,
                store=store,
                chariot=FakeChariot(),
                settings=_settings(),
                payload={"inbox_key": "inbox/ais", "filename": "ais.json"},
            ),
        )
        count = session.scalar(select(func.count()).select_from(AisReport))
    assert count == 1
    assert result["evidence"]["storage"] == "metadata.ais_reports"
    assert "inbox/ais" not in store.objects
