import json

from app.aggregate import evidence_identifiers
from app.processors.fusion import fusion_message
from app.tools import normalize_insight_args
from app.normalize import (
    detection_records,
    fmv_inference_request,
    model_id_from_watchbox,
    triage_event_row,
    watchbox_detection_row,
)


def test_detection_records_from_nested_inference_list():
    inference_id, rows = detection_records(
        {
            "inference_id": "inf-nested",
            "inference": [
                [
                    {
                        "label": " ship",
                        "score": 1,
                        "xmin": 59,
                        "ymin": 63,
                        "xmax": 1127,
                        "ymax": 681,
                    }
                ]
            ],
        }
    )
    assert inference_id == "inf-nested"
    assert rows[0]["label"] == "ship"
    assert rows[0]["geometry"]["xmin"] == 59
    assert rows[0]["geometry"]["ymax"] == 681


def test_detection_records_from_json_string():
    inference_id, rows = detection_records(
        {
            "inference_id": "inf-json",
            "inference": '[{"label": "vehicle", "score": 0.4, "box": {"xmin": 1, "ymin": 2, "xmax": 3, "ymax": 4}}]',
        }
    )
    assert inference_id == "inf-json"
    assert rows[0]["label"] == "vehicle"
    assert rows[0]["geometry"]["xmax"] == 3


def test_detection_records_from_label_arrays():
    inference_id, rows = detection_records(
        {
            "inference_id": "inf-1",
            "inference": {
                "detection_labels": ["vehicle"],
                "detection_scores": [0.91],
                "detection_boxes": [[1, 2, 3, 4]],
            },
        }
    )
    assert inference_id == "inf-1"
    assert rows[0]["label"] == "vehicle"
    assert rows[0]["score"] == 0.91
    assert rows[0]["geometry"]["bbox"] == [1, 2, 3, 4]


def test_fusion_message_uses_detection_and_vlm_outputs():
    message = fusion_message(
        {
            "asset_ids": ["asset-1"],
            "detection_ids": ["det-1"],
            "detections": [{"label": "ship", "score": 1, "bbox": {"xmin": 1, "ymin": 2, "xmax": 3, "ymax": 4}}],
            "visual_description": "A ship alongside a pier.",
        }
    )
    assert "A ship alongside a pier." in message
    assert "ship" in message
    assert "Write an insight" in message


def test_imagery_filename_extracts_vessel_name_and_imo():
    identifiers = evidence_identifiers(
        {
            "filename": "BELGOROD_IMO_9412359.webp",
            "visual_description": "A red cargo ship is visible on calm water.",
        }
    )
    assert identifiers == {
        "imo": ["9412359"],
        "mmsi": [],
        "vessel_name": ["BELGOROD"],
    }


def test_fusion_message_requires_aggregate_reasoning():
    message = fusion_message(
        {
            "aggregate_context": {
                "holdings_checked": ["vessel_ownership", "ais_reports"],
                "ownership": {"matches": [{"vessel_name": "BELGOROD"}]},
                "ais": {"matches": []},
            }
        }
    )
    assert "Reason over every non-empty match" in message
    assert "BELGOROD" in message
    assert "correct_insight" in message


def test_upsert_args_recover_subject_from_details_json():
    fields = normalize_insight_args(
        details_json=json.dumps(
            json.dumps(
                {
                    "vessel_name": "SEA DOLLARS",
                    "summary": "One AIS position for SEA DOLLARS.",
                    "entity_labels": ["vessel", "SEA DOLLARS"],
                    "latitude": "29.1",
                    "evidence": {"mmsi": "338167606"},
                }
            )
        )
    )
    assert fields["subject"] == "SEA DOLLARS"
    assert fields["summary"] == "One AIS position for SEA DOLLARS."
    assert fields["entity_labels"] == ["vessel", "SEA DOLLARS"]
    assert fields["latitude"] == 29.1
    assert fields["evidence"] == {"mmsi": "338167606"}


def test_upsert_args_accept_evidence_list():
    fields = normalize_insight_args(
        subject="SEA DOLLARS",
        evidence_json=[{"mmsi": "338167606", "vessel_name": "SEA DOLLARS"}],
    )
    assert fields["subject"] == "SEA DOLLARS"
    assert fields["evidence"]["records"][0]["mmsi"] == "338167606"


def test_ais_samples_are_search_identifiers():
    identifiers = evidence_identifiers(
        {
            "filename": "ais.json",
            "sample_mmsis": ["338167606"],
            "sample_vessel_names": ["SEA DOLLARS"],
        }
    )
    assert identifiers["mmsi"] == ["338167606"]
    assert identifiers["vessel_name"] == ["SEA DOLLARS"]
    assert identifiers["imo"] == []


def test_small_ais_message_uses_included_observations():
    message = fusion_message(
        {
            "storage": "metadata.ais_reports",
            "observations": [{"mmsi": "338167606", "vessel_name": "SEA DOLLARS"}],
        }
    )
    assert "observations are included" in message
    assert "SEA DOLLARS" in message


def test_watchbox_detection_mapping():
    row = watchbox_detection_row(
        {
            "id": "det-9",
            "classification": "ship",
            "score": 0.8,
            "lat": 21.3,
            "lon": -157.8,
            "inference_id": "inf-9",
            "model_id": "model-1",
            "time_of_emission": "2026-03-01T12:00:00Z",
            "triage_event": "event-1",
            "verification_status": "not_reviewed",
            "bbox": [0, 0, 10, 10],
        }
    )
    assert row["label"] == "ship"
    assert row["latitude"] == 21.3
    assert row["chariot_inference_id"] == "inf-9"
    assert row["triage_event_external_id"] == "event-1"
    assert row["observed_at"] is not None


def test_triage_event_mapping_uses_watch_point():
    row = triage_event_row(
        {
            "id": "event-1",
            "watchbox_id": "wp-1",
            "review_status": "not_reviewed",
            "date_created": "2026-03-01T12:00:00Z",
            "chariot_request": {"id": "req-1"},
            "imagery_request": {"id": "img-1", "imagery_date_captured": "2026-03-01T11:00:00Z"},
        },
        "wp-1",
    )
    assert row["watchpoint_id"] == "wp-1"
    assert row["chariot_ids"]["chariot_request"] == "req-1"
    assert row["captured_at"].isoformat().startswith("2026-03-01T11:00:00")


def test_model_id_from_watchbox():
    assert model_id_from_watchbox({"models": [{"id": "model-7"}]}) == "model-7"
    assert model_id_from_watchbox({"models": []}) is None


def test_fmv_filter_uses_feed_metadata():
    from datetime import datetime, timezone

    request = fmv_inference_request(
        datetime(2026, 3, 1, tzinfo=timezone.utc),
        datetime(2026, 3, 1, 1, tzinfo=timezone.utc),
        "feed-42",
    )
    metadata_filter = request["filters"]["metadata_filter"][0]
    assert metadata_filter == {"key": "feed_id", "operator": "=", "type": "string", "value": "feed-42"}
    assert request["filters"]["time_window_filter"]["start"] == "2026-03-01T00:00:00Z"
    assert request["filters"]["time_window_filter"]["end"] == "2026-03-01T01:00:00Z"
