from app.models import Detection
from app.normalize import fmv_inference_request
from app.processors.imagery import JobContext
from app.timeutil import parse_time


def process_fmv(ctx: JobContext) -> dict:
    payload = ctx.payload
    request = fmv_inference_request(
        parse_time(payload.get("time_start")),
        parse_time(payload.get("time_end")),
        payload["feed_id"],
    )
    rows = ctx.chariot.filter_inferences(payload["model_id"], request)
    detection_ids = []
    for row in rows:
        detection = Detection(
            label=row.get("label") or "unknown",
            score=row.get("score"),
            geometry=row.get("geometry"),
            latitude=row.get("latitude"),
            longitude=row.get("longitude"),
            chariot_inference_id=row.get("chariot_inference_id"),
            model_id=row.get("model_id") or payload["model_id"],
            attributes={"feed_id": payload["feed_id"], **(row.get("attributes") or {})},
            observed_at=row.get("observed_at"),
        )
        ctx.session.add(detection)
        ctx.session.flush()
        detection_ids.append(str(detection.id))
    ctx.session.commit()
    return {"evidence": {"detection_ids": detection_ids, "feed_id": payload["feed_id"]}}
