"""Normalize intelligence assessments into stored records."""

import json
import re
from datetime import datetime
from typing import Any

_MONTHS = "%B %d, %Y"
_IMO = re.compile(r"\bIMO[:\s#]*(\d{7})\b", re.IGNORECASE)
_MMSI = re.compile(r"\bMMSI[:\s#]*(\d{9})\b", re.IGNORECASE)
_LABEL = re.compile(r"^[•\-\*\s]*([A-Za-z][A-Za-z0-9 /_-]{0,60}):\s*(.+)$", re.MULTILINE)
_VESSEL = re.compile(r"\bM/?V\s+([A-Z0-9][A-Z0-9 .'-]*?)(?:\s*\(|\s*$)", re.IGNORECASE)
_ON_DATE = re.compile(r"\bOn\s+([A-Z][a-z]+ \d{1,2}, \d{4})\b")
_SUMMARY = re.compile(r"(?ms)^2\.\s*Basis for Investigation[^\n]*\n+\s*(.+?)(?=\n\s*A\.)")


def parse_intel_document(raw: bytes | str) -> list[dict]:
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    if not text.strip():
        raise ValueError("Intel report is empty")
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
        raise ValueError('Intel ingest expects a report object, a list, or {"reports": [...]}')
    records = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            records.append(_report_from_text(item.strip()))
        elif isinstance(item, dict):
            records.append(_report_from_mapping(item))
    if not records:
        raise ValueError("No intel reports could be stored")
    return records


def _report_from_mapping(item: dict) -> dict:
    body = _text(item.get("body") or item.get("text") or item.get("report"))
    parsed = _report_from_text(body) if body else _blank()
    for key in (
        "title",
        "classification",
        "subject",
        "person_name",
        "vessel_name",
        "imo",
        "mmsi",
        "status",
        "summary",
        "source",
    ):
        value = _text(item.get(key))
        if value:
            parsed[key] = value
    event_date = _date_text(item.get("event_date"))
    if event_date:
        parsed["event_date"] = event_date
    extras = item.get("details") if isinstance(item.get("details"), dict) else {}
    parsed["details"] = {**parsed["details"], **extras}
    if not parsed["body"]:
        raise ValueError("Each intel report needs a body")
    parsed["report_key"] = _report_key(parsed)
    return parsed


def _report_from_text(text: str) -> dict:
    labels = {match.group(1).strip().casefold(): match.group(2).strip() for match in _LABEL.finditer(text)}
    subject = _text(labels.get("subject"))
    full_name = _text(labels.get("full name"))
    vessel = _vessel_name(text)
    dated = _ON_DATE.search(text)
    record = {
        "title": _title(text),
        "classification": _text(labels.get("classification")),
        "subject": subject,
        "person_name": _person_name(full_name or subject),
        "vessel_name": vessel,
        "imo": _first_group(_IMO, text),
        "mmsi": _first_group(_MMSI, text),
        "status": _text(labels.get("status")),
        "event_date": _date_text(dated.group(1) if dated else None),
        "summary": _summary(text),
        "body": text,
        "source": _text(labels.get("source")),
        "details": _details(text, labels),
    }
    record["report_key"] = _report_key(record)
    return record


def _blank() -> dict:
    return {
        "title": None,
        "classification": None,
        "subject": None,
        "person_name": None,
        "vessel_name": None,
        "imo": None,
        "mmsi": None,
        "status": None,
        "event_date": None,
        "summary": None,
        "body": "",
        "source": None,
        "details": {},
    }


def _title(text: str) -> str | None:
    for line in text.splitlines():
        candidate = line.strip()
        if candidate and ":" not in candidate:
            return candidate
    return None


def _person_name(value: str | None) -> str | None:
    text = _text(value)
    if text is None:
        return None
    text = re.sub(r"^\s*Captain\s+", "", text, flags=re.IGNORECASE)
    text = re.split(r"\s+[–—-]\s+", text, maxsplit=1)[0]
    return _text(text)


def _vessel_name(text: str) -> str | None:
    match = _VESSEL.search(text)
    if not match:
        return None
    return _text(match.group(1))


def _details(text: str, labels: dict[str, str]) -> dict:
    details: dict[str, Any] = {}
    born = _date_text(_strip_paren(labels.get("date of birth")))
    if born:
        details["date_of_birth"] = born
    nationality = _strip_paren(labels.get("nationality"))
    if nationality:
        details["nationality"] = nationality
    for key, label in (
        ("credentials", "credentials"),
        ("association", "association"),
    ):
        value = _text(labels.get(label))
        if value:
            details[key] = value
    operator = re.search(r'OOO\s+"([^"]+)"', text)
    if operator:
        details["operator"] = operator.group(1)
    if re.search(r"\bMaster of\b", text, re.IGNORECASE):
        details["role"] = "Master"
    sister = re.search(r"(?i:sister ship)\s+([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)*)", text)
    if sister:
        details["sister_vessel"] = sister.group(1).strip(" .")
    cargo = re.search(r"([\d,]+)\s*MT of\s+([^,\n]+)", text, re.IGNORECASE)
    if cargo:
        details["cargo"] = f"{cargo.group(1)} MT of {cargo.group(2).strip()}"
    return details


def _summary(text: str) -> str | None:
    match = _SUMMARY.search(text)
    if not match:
        return None
    summary = " ".join(match.group(1).split())
    return summary or None


def _report_key(record: dict) -> str:
    person = _slug(record.get("person_name") or record.get("subject") or "subject")
    title = _slug(record.get("title") or "intel-report")
    return ":".join(part for part in (record.get("imo") or "unknown", person, title) if part)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:80]


def _strip_paren(value: str | None) -> str | None:
    text = _text(value)
    if text is None:
        return None
    return _text(re.sub(r"\s*\(.*\)\s*$", "", text))


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
