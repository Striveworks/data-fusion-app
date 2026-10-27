"""Normalize open-source intelligence reports into stored records."""

import json
import re
from datetime import datetime
from typing import Any

_MONTHS = "%B %d, %Y"
_IMO = re.compile(r"\bIMO[:\s#]*(\d{7})\b", re.IGNORECASE)
_MMSI = re.compile(r"\bMMSI[:\s#]*(\d{9})\b", re.IGNORECASE)
_IMO_MMSI = re.compile(r"\b(\d{7})\s*/\s*(\d{9})\b")
_DMS = re.compile(
    r"(\d+)\s*°\s*(\d+)\s*'\s*([\d.]+)\s*(?:\"|″)?\s*([NSEW])",
    re.IGNORECASE,
)
_LABEL = re.compile(r"^[•\-\*\s]*([A-Za-z][A-Za-z0-9 /_-]{0,40}):\s*(.+)$", re.MULTILINE)
_SECTION = re.compile(r"(?ms)^1\.\s*Executive Summary\s*(.*?)^\s*2\.")


def parse_osint_document(raw: bytes | str) -> list[dict]:
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    if not text.strip():
        raise ValueError("OSINT report is empty")
    stripped = text.strip()
    if stripped[0] in "[{":
        try:
            body = json.loads(stripped)
        except json.JSONDecodeError:
            body = None
        if body is not None:
            return records_from_body(body)
    return [_report_from_text(stripped)]


def records_from_body(body: Any) -> list[dict]:
    if isinstance(body, list):
        raw = body
    elif isinstance(body, dict) and isinstance(body.get("reports"), list):
        raw = body["reports"]
    elif isinstance(body, dict):
        raw = [body]
    else:
        raise ValueError('OSINT ingest expects a report object, a list, or {"reports": [...]}')
    records = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            records.append(_report_from_text(item.strip()))
        elif isinstance(item, dict):
            records.append(_report_from_mapping(item))
    if not records:
        raise ValueError("No OSINT reports could be stored")
    return records


def _report_from_mapping(item: dict) -> dict:
    body = _text(item.get("body") or item.get("text") or item.get("report"))
    parsed = _report_from_text(body) if body else _blank()
    for key in (
        "title",
        "vessel_name",
        "imo",
        "mmsi",
        "flag",
        "vessel_type",
        "event",
        "origin",
        "destination",
        "summary",
        "source",
    ):
        value = _text(item.get(key))
        if value:
            parsed[key] = value
    for key in ("event_date", "report_date"):
        value = _date_text(item.get(key))
        if value:
            parsed[key] = value
    for key in ("latitude", "longitude"):
        value = _number(item.get(key))
        if value is not None:
            parsed[key] = value
    extras = item.get("details") if isinstance(item.get("details"), dict) else {}
    parsed["details"] = {**parsed["details"], **extras}
    if not parsed["body"]:
        raise ValueError("Each OSINT report needs a body")
    parsed["report_key"] = _report_key(parsed)
    return parsed


def _report_from_text(text: str) -> dict:
    labels = {match.group(1).strip().casefold(): match.group(2).strip() for match in _LABEL.finditer(text)}
    title = _title(text)
    identified = labels.get("vessel identified", "")
    vessel_name = _vessel_name(labels.get("vessel name") or identified)
    imo = _first_group(_IMO, text)
    mmsi = _first_group(_MMSI, text)
    pair = _IMO_MMSI.search(text)
    if pair:
        imo = imo or pair.group(1)
        mmsi = mmsi or pair.group(2)
    flag, vessel_type = _flag_and_type(labels.get("flag / type"))
    latitude, longitude = _coordinates(text)
    record = {
        "title": title,
        "vessel_name": vessel_name,
        "imo": imo,
        "mmsi": mmsi,
        "flag": flag,
        "vessel_type": vessel_type,
        "event": _text(labels.get("event")),
        "event_date": _date_text(labels.get("date of event")),
        "report_date": _date_text(labels.get("report date")),
        "origin": _place_after(text, r"port of"),
        "destination": _place_after(text, r"bound for"),
        "latitude": latitude,
        "longitude": longitude,
        "summary": _summary(text),
        "body": text,
        "source": "unclassified open-source intelligence",
        "details": _details(text),
    }
    record["report_key"] = _report_key(record)
    return record


def _blank() -> dict:
    return {
        "title": None,
        "vessel_name": None,
        "imo": None,
        "mmsi": None,
        "flag": None,
        "vessel_type": None,
        "event": None,
        "event_date": None,
        "report_date": None,
        "origin": None,
        "destination": None,
        "latitude": None,
        "longitude": None,
        "summary": None,
        "body": "",
        "source": "unclassified open-source intelligence",
        "details": {},
    }


def _title(text: str) -> str | None:
    for line in text.splitlines():
        candidate = line.strip()
        if candidate and ":" not in candidate:
            return candidate
    return None


def _vessel_name(value: str | None) -> str | None:
    text = _text(value)
    if text is None:
        return None
    text = re.sub(r"^\s*M/?V\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(IMO:.*$", "", text, flags=re.IGNORECASE).strip()
    return text or None


def _flag_and_type(value: str | None) -> tuple[str | None, str | None]:
    text = _text(value)
    if text is None or "/" not in text:
        return text, None
    flag, vessel_type = text.split("/", 1)
    return _text(flag), _text(vessel_type)


def _coordinates(text: str) -> tuple[float | None, float | None]:
    latitude = None
    longitude = None
    for degrees, minutes, seconds, hemisphere in _DMS.findall(text):
        value = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
        if hemisphere.upper() in {"S", "W"}:
            value = -value
        value = round(value, 6)
        if hemisphere.upper() in {"N", "S"} and latitude is None:
            latitude = value
        elif hemisphere.upper() in {"E", "W"} and longitude is None:
            longitude = value
    return latitude, longitude


def _place_after(text: str, prefix: str) -> str | None:
    match = re.search(prefix + r"\s+([A-Z][A-Za-z .'-]+)", text)
    if not match:
        return None
    place = re.split(r",|\.|\s+bound\b", match.group(1), maxsplit=1)[0]
    return _text(place)


def _summary(text: str) -> str | None:
    match = _SECTION.search(text)
    if not match:
        return None
    summary = " ".join(match.group(1).split())
    return summary or None


def _details(text: str) -> dict:
    details: dict[str, Any] = {}
    draught = re.search(r"Reported Draught:\s*([\d.]+)", text, re.IGNORECASE)
    if draught:
        details["draught_m"] = float(draught.group(1))
    dimensions = re.search(r"(\d+(?:\.\d+)?)\s*m\s*[×x]\s*(\d+(?:\.\d+)?)\s*m", text, re.IGNORECASE)
    if dimensions:
        details["length_m"] = float(dimensions.group(1))
        details["breadth_m"] = float(dimensions.group(2))
    header = re.search(r"destination header of\s+([A-Z0-9 ]+)", text, re.IGNORECASE)
    if header:
        details["destination_code"] = header.group(1).strip()
    eta = re.search(
        r"Estimated Time of Arrival \(ETA\) of\s+([A-Z][a-z]+ \d{1,2}) at (\d{2}:\d{2}) UTC",
        text,
    )
    if eta:
        details["eta"] = f"{eta.group(1)} {eta.group(2)} UTC"
    return details


def _report_key(record: dict) -> str:
    title = _slug(record.get("title") or record.get("event") or "osint-report")
    return ":".join(
        part
        for part in (record.get("imo") or "unknown", record.get("event_date") or "undated", title)
        if part
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:80]


def _first_group(pattern: re.Pattern, text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def _date_text(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    try:
        return datetime.strptime(text, _MONTHS).date().isoformat()
    except ValueError:
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
