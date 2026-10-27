"""Normalize Automatic Identification System reports from ingest payloads."""

from dataclasses import dataclass, field
from typing import Any

from app.timeutil import parse_time

_ALIASES = {
    "mmsi": "mmsi",
    "tstamp": "timestamp",
    "timestamp": "timestamp",
    "time": "timestamp",
    "latitude": "latitude",
    "lat": "latitude",
    "longitude": "longitude",
    "lon": "longitude",
    "cog": "course_over_ground_degrees",
    "course_over_ground_degrees": "course_over_ground_degrees",
    "sog": "speed_over_ground_knots",
    "speed_over_ground_knots": "speed_over_ground_knots",
    "heading": "heading_degrees",
    "heading_degrees": "heading_degrees",
    "navstat": "navigational_status_code",
    "navigational_status_code": "navigational_status_code",
    "navigational_status": "navigational_status",
    "imo": "imo",
    "name": "vessel_name",
    "vessel_name": "vessel_name",
    "callsign": "call_sign",
    "call_sign": "call_sign",
    "type": "vessel_type",
    "vessel_type": "vessel_type",
    "vessel_type_cargo": "vessel_type_cargo",
    "draught": "draft",
    "draft": "draft",
    "dest": "destination",
    "destination": "destination",
    "eta": "eta",
    "length": "length",
    "width": "width",
}

_NAV_STATUS = {
    0: "Underway using engine",
    1: "At anchor",
    2: "Not under command",
    3: "Restricted manoeuvrability",
    4: "Constrained by her draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in fishing",
    8: "Under way sailing",
    14: "AIS-SART",
    15: "Not defined",
}


@dataclass
class AisParseResult:
    reports: list[dict] = field(default_factory=list)
    skipped: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)


def reports_from_body(body: Any) -> list[dict]:
    """Accept one report, a list of reports, or {"reports": [...]}."""
    result = parse_ais(body)
    if not result.reports:
        detail = "No AIS reports could be stored"
        if result.skip_reasons:
            reasons = ", ".join(f"{count} {reason}" for reason, count in sorted(result.skip_reasons.items()))
            detail = f"{detail} ({reasons})"
        raise ValueError(detail)
    return result.reports


def parse_ais_document(raw: bytes | str) -> AisParseResult:
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    if not text.strip():
        raise ValueError("AIS file is empty")
    try:
        body = json_loads(text)
    except ValueError as exc:
        raise ValueError("AIS body must be JSON") from exc
    return parse_ais(body)


def json_loads(text: str) -> Any:
    import json

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("AIS body must be JSON") from exc


def parse_ais(body: Any) -> AisParseResult:
    """Normalize a friendly report or a standard AIS feed array.

    Rows missing an MMSI or a usable timestamp are skipped. Other missing
    fields are stored as empty values.
    """
    result = AisParseResult()
    for item in _raw_reports(body):
        if not isinstance(item, dict):
            _skip(result, "not_an_object")
            continue
        try:
            report = _report(item)
        except _Skip as exc:
            _skip(result, exc.reason)
            continue
        result.reports.append(report)
    return result


class _Skip(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _raw_reports(body: Any) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body, dict) and isinstance(body.get("reports"), list):
        return body["reports"]
    if isinstance(body, dict) and _has_mmsi(body):
        return [body]
    if isinstance(body, dict):
        return [body]
    raise ValueError('AIS ingest expects a report object, a list of reports, or {"reports": [...]}')


def _has_mmsi(item: dict) -> bool:
    return any(str(key).strip().lower() == "mmsi" for key in item)


def _skip(result: AisParseResult, reason: str) -> None:
    result.skipped += 1
    result.skip_reasons[reason] = result.skip_reasons.get(reason, 0) + 1


def _report(item: dict) -> dict:
    canonical: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    dims: dict[str, Any] = {}
    for key, value in item.items():
        folded = str(key).strip().lower()
        if folded in {"a", "b", "c", "d"}:
            dims[folded] = value
            extras[folded] = value
            continue
        target = _ALIASES.get(folded)
        if target is None:
            extras[key] = value
        elif target not in canonical or canonical[target] in (None, ""):
            canonical[target] = value

    mmsi = _identifier(canonical.get("mmsi"))
    if mmsi is None:
        raise _Skip("missing_mmsi")
    observed = _parse_timestamp(canonical.get("timestamp"))
    if observed is None:
        raise _Skip("missing_timestamp")

    status_code = _integer(canonical.get("navigational_status_code"))
    status = _text(canonical.get("navigational_status"))
    if status is None and status_code is not None:
        status = _NAV_STATUS.get(status_code)
    length = _number(canonical.get("length"))
    width = _number(canonical.get("width"))
    if length is None:
        length = _span(dims.get("a"), dims.get("b"))
    if width is None:
        width = _span(dims.get("c"), dims.get("d"))

    return {
        "mmsi": mmsi,
        "vessel_name": _text(canonical.get("vessel_name")),
        "call_sign": _text(canonical.get("call_sign")),
        "imo": _identifier(canonical.get("imo")),
        "vessel_type": _integer(canonical.get("vessel_type")),
        "vessel_type_cargo": _text(canonical.get("vessel_type_cargo")),
        "length": length,
        "width": width,
        "draft": _number(canonical.get("draft")),
        "observed_at": observed.isoformat(),
        "latitude": _number(canonical.get("latitude")),
        "longitude": _number(canonical.get("longitude")),
        "speed_over_ground_knots": _number(canonical.get("speed_over_ground_knots")),
        "course_over_ground_degrees": _number(canonical.get("course_over_ground_degrees")),
        "heading_degrees": _number(canonical.get("heading_degrees")),
        "navigational_status_code": status_code,
        "navigational_status": status,
        "destination": _text(canonical.get("destination")),
        "eta": _text(canonical.get("eta")),
        "details": extras,
    }


def _parse_timestamp(value: Any):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        try:
            return parse_time(value)
        except ValueError:
            return None
    text = value.strip()
    for suffix in (" GMT", " UTC"):
        if text.upper().endswith(suffix):
            text = text[: -len(suffix)].strip()
    try:
        return parse_time(text)
    except ValueError:
        return None


def _identifier(value: Any) -> str | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text or None


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


def _integer(value: Any) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not number.is_integer():
        return None
    return int(number)


def _span(bow: Any, stern: Any) -> float | None:
    start = _number(bow)
    end = _number(stern)
    if start is None or end is None:
        return None
    return start + end
