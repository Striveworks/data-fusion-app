"""Normalize scraped vessel ownership records."""

from typing import Any

_PLACEHOLDERS = {"", "n/a", "na", "none", "null", "-"}

_FIELDS = {
    "vessel_name",
    "category",
    "imo",
    "flag_current",
    "mmsi",
    "call_sign",
    "vessel_type",
    "length_m",
    "gross_tonnage",
    "dwt",
    "sanctions",
    "sanction_links",
    "sanctions_person",
    "picture_filename",
    "source_url",
    "main_photo_url",
}


def records_from_body(body: Any) -> list[dict]:
    if isinstance(body, list):
        raw = body
    elif isinstance(body, dict) and isinstance(body.get("records"), list):
        raw = body["records"]
    elif isinstance(body, dict) and ("vessel_name" in body or "source_url" in body or "imo" in body):
        raw = [body]
    else:
        raise ValueError('Ownership ingest expects a vessel object, a list, or {"records": [...]}')
    records = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        record = _record(item)
        if record["vessel_name"] or record["imo"] or record["mmsi"] or record["source_url"]:
            records.append(record)
    if not records:
        raise ValueError("No ownership records could be stored")
    return records


def parse_ownership_document(raw: bytes | str) -> list[dict]:
    import json

    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    if not text.strip():
        raise ValueError("Ownership file is empty")
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Ownership body must be JSON") from exc
    return records_from_body(body)


def _record(item: dict) -> dict:
    extras = {key: value for key, value in item.items() if key not in _FIELDS}
    links = item.get("sanction_links")
    if not isinstance(links, list):
        links = []
    return {
        "vessel_name": _text(item.get("vessel_name")),
        "category": _text(item.get("category")),
        "imo": _text(item.get("imo")),
        "flag_current": _text(item.get("flag_current")),
        "mmsi": _text(item.get("mmsi")),
        "call_sign": _text(item.get("call_sign")),
        "vessel_type": _text(item.get("vessel_type")),
        "length_m": _number(item.get("length_m")),
        "gross_tonnage": _number(item.get("gross_tonnage")),
        "dwt": _number(item.get("dwt")),
        "sanctions": _text(item.get("sanctions")),
        "sanction_links": [str(link) for link in links if link],
        "sanctions_person": _text(item.get("sanctions_person")),
        "picture_filename": _text(item.get("picture_filename")),
        "source_url": _text(item.get("source_url")),
        "main_photo_url": _text(item.get("main_photo_url")),
        "details": extras,
    }


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _PLACEHOLDERS:
        return None
    return text


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text.lower() in _PLACEHOLDERS:
        return None
    try:
        return float(text)
    except ValueError:
        return None
