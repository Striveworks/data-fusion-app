import uuid

from app.models import Detection, TriageEvent
from app.normalize import fmv_inference_request
from app.processors.imagery import JobContext


def process_watchpoint(ctx: JobContext) -> dict:
    payload = ctx.payload
    watchpoint_id = payload["watchpoint_id"]
    project_id = payload["project_id"]
    events = ctx.chariot.list_triage_events(
        project_id,
        watchpoint_id,
        payload.get("time_start"),
        payload.get("time_end"),
    )
    event_ids_by_external: dict[str, uuid.UUID] = {}
    triage_ids: list[str] = []
    for event in events:
        row = TriageEvent(
            watchpoint_id=event["watchpoint_id"],
            chariot_event_id=event.get("chariot_event_id"),
            review_status=event.get("review_status"),
            captured_at=event.get("captured_at"),
            chariot_ids=event.get("chariot_ids") or {},
            details=event.get("details") or {},
        )
        ctx.session.add(row)
        ctx.session.flush()
        triage_ids.append(str(row.id))
        if event.get("chariot_event_id"):
            event_ids_by_external[str(event["chariot_event_id"])] = row.id

    detections = ctx.chariot.list_watchpoint_detections(
        watchpoint_id,
        payload.get("time_start"),
        payload.get("time_end"),
    )
    model_id = ctx.chariot.watchbox_model_id(watchpoint_id)
    if model_id:
        detections.extend(
            ctx.chariot.filter_inferences(model_id, watchpoint_inference_request(payload, watchpoint_id))
        )

    detection_ids = _insert_detections(ctx, detections, event_ids_by_external, model_id)
    ctx.session.commit()
    return {
        "evidence": {
            "triage_event_ids": triage_ids,
            "detection_ids": detection_ids,
            "watchpoint_id": watchpoint_id,
        }
    }


def watchpoint_inference_request(payload: dict, feed_key: str) -> dict:
    from app.timeutil import parse_time

    request = fmv_inference_request(
        parse_time(payload.get("time_start")),
        parse_time(payload.get("time_end")),
        feed_key,
    )
    request["filters"]["metadata_filter"] = [
        {"key": "watchpoint_id", "operator": "=", "type": "string", "value": feed_key}
    ]
    return request


def _insert_detections(ctx: JobContext, detections: list[dict], event_ids: dict, model_id: str | None) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for row in detections:
        inference_id = row.get("chariot_inference_id")
        dedupe_key = f"{inference_id}:{row.get('label')}:{row.get('geometry')}"
        if inference_id and dedupe_key in seen:
            continue
        if inference_id:
            seen.add(dedupe_key)
        external_event = row.get("triage_event_external_id")
        if external_event is None:
            attributes = row.get("attributes") or {}
            external_event = attributes.get("triage_event")
        detection = Detection(
            triage_event_id=event_ids.get(str(external_event)) if external_event else None,
            label=row.get("label") or "unknown",
            score=row.get("score"),
            geometry=row.get("geometry"),
            latitude=row.get("latitude"),
            longitude=row.get("longitude"),
            chariot_inference_id=inference_id,
            model_id=row.get("model_id") or model_id,
            attributes=row.get("attributes") or {},
            observed_at=row.get("observed_at"),
        )
        ctx.session.add(detection)
        ctx.session.flush()
        ids.append(str(detection.id))
    return ids
