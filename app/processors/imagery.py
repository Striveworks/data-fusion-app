import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.chariot import ChariotGateway, DescriptionUnsupported, suffix_for
from app.config import Settings
from app.models import Asset, Detection
from app.normalize import detection_records
from app.storage import ObjectStore
from app.timeutil import parse_time


def _bbox(geometry: dict | None) -> dict | list | None:
    if not geometry:
        return None
    if geometry.get("bbox") is not None and not any(
        geometry.get(key) is not None for key in ("xmin", "ymin", "xmax", "ymax")
    ):
        return geometry["bbox"]
    corners = {
        key: geometry[key] for key in ("xmin", "ymin", "xmax", "ymax") if geometry.get(key) is not None
    }
    return corners or geometry.get("bbox")


@dataclass
class JobContext:
    session: Session
    timescale: Session
    store: ObjectStore
    chariot: ChariotGateway
    settings: Settings
    payload: dict


def process_imagery(ctx: JobContext) -> dict:
    payload = ctx.payload
    inbox_key = payload["inbox_key"]
    data = ctx.store.get(inbox_key)
    asset_id = uuid.uuid4()
    suffix = suffix_for(payload.get("content_type"), payload.get("filename"))
    object_key = f"imagery/{asset_id}{suffix}"
    ctx.store.put(object_key, data, payload.get("content_type") or "application/octet-stream")
    details = dict(payload.get("metadata") or {})
    asset = Asset(
        id=asset_id,
        modality=payload["modality"],
        captured_at=parse_time(payload.get("captured_at")),
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
        footprint=payload.get("footprint"),
        details=details,
        bucket=ctx.settings.minio_bucket,
        object_key=object_key,
        source_kind="imagery",
        external_id=payload.get("external_id"),
    )
    ctx.session.add(asset)
    ctx.session.commit()
    ctx.store.delete(inbox_key)

    model_id = ctx.settings.chariot_detection_model_id
    if not model_id:
        raise RuntimeError("CHARIOT_DETECTION_MODEL_ID is unset")

    raw = ctx.chariot.detect(model_id, data, suffix=suffix)
    inference_id, rows = detection_records(raw)
    detection_ids = []
    detection_summary = []
    for row in rows:
        detection = Detection(
            asset_id=asset.id,
            label=row["label"],
            score=row.get("score"),
            geometry=row.get("geometry"),
            latitude=row.get("latitude") if row.get("latitude") is not None else asset.latitude,
            longitude=row.get("longitude") if row.get("longitude") is not None else asset.longitude,
            chariot_inference_id=row.get("chariot_inference_id") or inference_id,
            model_id=model_id,
            attributes=row.get("attributes") or {},
            observed_at=row.get("observed_at") or asset.captured_at,
        )
        ctx.session.add(detection)
        ctx.session.flush()
        detection_ids.append(str(detection.id))
        detection_summary.append(
            {
                "detection_id": str(detection.id),
                "label": row["label"],
                "score": row.get("score"),
                "bbox": _bbox(row.get("geometry")),
            }
        )

    description, vlm_status = _visual_description(ctx, data, suffix)
    details = dict(asset.details or {})
    details["detection_model_id"] = model_id
    details["inference_id"] = inference_id
    details["visual_description_status"] = vlm_status
    if description:
        details["visual_description"] = description
        details["vlm_model_id"] = ctx.settings.chariot_vlm_model_id
    asset.details = details
    ctx.session.commit()
    evidence = {
        "asset_ids": [str(asset.id)],
        "detection_ids": detection_ids,
        "detection_model_id": model_id,
        "inference_id": inference_id,
        "detections": detection_summary,
        "modality": asset.modality,
        "filename": payload.get("filename"),
        "captured_at": payload.get("captured_at"),
        "latitude": asset.latitude,
        "longitude": asset.longitude,
        "vlm_model_id": ctx.settings.chariot_vlm_model_id or None,
        "visual_description_status": vlm_status,
        "visual_description": description,
    }
    return {"evidence": evidence}


def _visual_description(ctx: JobContext, data: bytes, suffix: str) -> tuple[str | None, str]:
    model_id = ctx.settings.chariot_vlm_model_id
    if not model_id:
        return None, "not_configured"
    prompt = (
        "Describe the objects, counts, activity, and setting visible in this image. "
        "Only describe what is visible."
    )
    try:
        description = ctx.chariot.describe_image(model_id, data, prompt, suffix=suffix)
    except DescriptionUnsupported:
        return None, "detection_only"
    except Exception as exc:
        return None, f"error: {exc}"
    text = description.strip()
    return (text or None), "ok"
