"""Plain-dict conversions shared by the Chariot gateway and the worker."""

import json
from datetime import datetime
from typing import Any

from app.timeutil import chariot_window, parse_time


def _as_dict(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items() if not key.startswith("_")}
    return {}


def detection_records(result: Any) -> tuple[str | None, list[dict]]:
    """Normalize a Chariot detect response into row-shaped detection dicts."""
    payload = _as_dict(result) if not isinstance(result, list) else {"inference": result}
    inference_id = payload.get("inference_id")
    rows = [_box_row(item, inference_id) for item in _detection_items(payload)]
    rows = [row for row in rows if row is not None]
    if rows:
        return inference_id, rows

    inference = _parse_json_value(payload.get("inference", payload))
    data = _as_dict(inference)
    labels = data.get("detection_labels") or []
    scores = data.get("detection_scores") or []
    boxes = data.get("detection_boxes") or []
    for index, label in enumerate(labels):
        score = scores[index] if index < len(scores) else None
        box = boxes[index] if index < len(boxes) else None
        text = str(label).strip()
        if not text:
            continue
        rows.append(
            {
                "label": text,
                "score": score,
                "geometry": {"bbox": box} if box is not None else None,
                "chariot_inference_id": inference_id,
                "latitude": None,
                "longitude": None,
                "attributes": {},
            }
        )
    return inference_id, rows


def _detection_items(payload: dict) -> list[Any]:
    inference = payload.get("inference", payload)
    items = _coerce_boxes(inference)
    sources = [_as_dict(_parse_json_value(inference))]
    if "inference" in payload:
        sources.append(payload)
    seen: set[int] = set()
    for source in sources:
        marker = id(source)
        if marker in seen:
            continue
        seen.add(marker)
        for key in ("object_detection", "oriented_object_detection"):
            items.extend(_coerce_boxes(source.get(key)))
    return items


def _coerce_boxes(value: Any) -> list[Any]:
    value = _parse_json_value(value)
    if isinstance(value, list):
        boxes: list[Any] = []
        for item in value:
            boxes.extend(_coerce_boxes(item))
        return boxes
    data = _as_dict(value)
    if any(data.get(key) for key in ("label", "classification", "class_label")):
        return [data]
    return []


def _parse_json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _flatten_box(data: dict) -> dict:
    box = data.get("box")
    if not isinstance(box, dict):
        nested = data.get("bbox")
        box = nested if isinstance(nested, dict) else None
    if not isinstance(box, dict):
        return data
    merged = dict(data)
    for key in ("xmin", "ymin", "xmax", "ymax"):
        if merged.get(key) is None and box.get(key) is not None:
            merged[key] = box[key]
    return merged


def _box_row(item: Any, inference_id: str | None) -> dict | None:
    data = _as_dict(item)
    if not data:
        return None
    data = _flatten_box(data)
    label = data.get("label") or data.get("classification") or data.get("class_label")
    label = str(label).strip() if label is not None else ""
    if not label:
        return None
    bbox = {
        key: data[key]
        for key in ("xmin", "ymin", "xmax", "ymax", "bbox")
        if data.get(key) is not None
    }
    return {
        "label": str(label),
        "score": data.get("score"),
        "geometry": bbox or None,
        "chariot_inference_id": data.get("inference_id") or inference_id,
        "latitude": data.get("lat", data.get("latitude")),
        "longitude": data.get("lon", data.get("longitude")),
        "attributes": {
            key: data[key]
            for key in ("verification_status", "id", "source_detection")
            if data.get(key) is not None
        },
        "observed_at": parse_time(data.get("time_of_emission") or data.get("observed_at")),
        "model_id": data.get("model_id"),
    }


def watchbox_detection_row(item: Any) -> dict:
    data = _as_dict(item)
    geometry = None
    if data.get("bbox") is not None:
        geometry = {"bbox": data["bbox"]}
    elif data.get("area") is not None:
        geometry = {"area": data["area"]}
    return {
        "label": str(data.get("classification") or data.get("label") or "unknown"),
        "score": data.get("score"),
        "geometry": geometry,
        "latitude": data.get("lat"),
        "longitude": data.get("lon"),
        "chariot_inference_id": data.get("inference_id") or data.get("inference_store_detection_id"),
        "model_id": data.get("model_id"),
        "observed_at": parse_time(data.get("time_of_emission")),
        "attributes": {
            "watchbox_detection_id": data.get("id"),
            "verification_status": data.get("verification_status"),
            "triage_event": data.get("triage_event"),
        },
        "triage_event_external_id": data.get("triage_event"),
    }


def triage_event_row(item: Any, watchpoint_id: str) -> dict:
    data = _as_dict(item)
    imagery = data.get("imagery_request")
    captured = None
    if isinstance(imagery, dict):
        captured = imagery.get("imagery_date_captured") or imagery.get("date_captured")
    return {
        "watchpoint_id": data.get("watchbox_id") or watchpoint_id,
        "chariot_event_id": data.get("id"),
        "review_status": data.get("review_status"),
        "captured_at": parse_time(captured or data.get("date_created")),
        "chariot_ids": {
            "chariot_request": _identifier(data.get("chariot_request")),
            "imagery_request": _identifier(imagery),
        },
        "details": {"task_type": data.get("task_type"), "area": data.get("area")},
    }


def _identifier(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    data = _as_dict(value)
    identifier = data.get("id")
    return str(identifier) if identifier else None


def model_id_from_watchbox(watchbox: Any) -> str | None:
    data = _as_dict(watchbox)
    models = data.get("models") or []
    if isinstance(models, dict):
        models = [models]
    for model in models:
        if isinstance(model, str) and model:
            return model
        model_data = _as_dict(model)
        identifier = model_data.get("id") or model_data.get("model_id")
        if identifier:
            return str(identifier)
    return None


def fmv_inference_request(
    start: datetime | None,
    end: datetime | None,
    feed_id: str,
) -> dict:
    return {
        "filters": {
            "time_window_filter": chariot_window(start, end),
            "metadata_filter": [
                {"key": "feed_id", "operator": "=", "type": "string", "value": feed_id}
            ],
        },
        "pagination": {"limit": 200, "sort": "created_at", "direction": "desc"},
    }


def inference_store_rows(inference: Any) -> list[dict]:
    data = _as_dict(inference)
    inference_id = data.get("inference_id")
    observed_at = parse_time(data.get("created_at"))
    coordinates = _as_dict(data.get("data_coordinates"))
    latitude = coordinates.get("latitude")
    longitude = coordinates.get("longitude")
    contracts = data.get("object_detection") or data.get("oriented_object_detection") or []
    rows = []
    for contract in contracts:
        row = _box_row(contract, inference_id)
        if row is None:
            continue
        row["observed_at"] = row.get("observed_at") or observed_at
        row["latitude"] = row.get("latitude") if row.get("latitude") is not None else latitude
        row["longitude"] = row.get("longitude") if row.get("longitude") is not None else longitude
        row["model_id"] = row.get("model_id") or data.get("model_id")
        rows.append(row)
    return rows
