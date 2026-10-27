"""Normalize ELINT intercept collections into signal samples."""

import json
from typing import Any


def parse_elint_document(raw: bytes | str) -> list[dict]:
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    if not text.strip():
        return []
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = _rows(body)
    if rows is None:
        return []
    samples = []
    for item in rows:
        if isinstance(item, dict):
            sample = _sample(item)
            if sample is not None:
                samples.append(sample)
    return samples


_ROW_KEYS = {
    "intercept_id",
    "INTERCEPT_ID",
    "ELINT_NOTATION",
    "elint_notation",
    "timestamp",
    "TSTAMP",
}


def _rows(body: Any) -> list | None:
    if isinstance(body, dict):
        for key in ("elint_intercept_collection", "intercepts", "elint"):
            rows = body.get(key)
            if isinstance(rows, list):
                return rows
        return None
    if isinstance(body, list) and body and isinstance(body[0], dict) and _ROW_KEYS.intersection(body[0]):
        return body
    return None


def _sample(item: dict) -> dict | None:
    observed = _timestamp(_first(item, "timestamp", "time", "TSTAMP"))
    if not observed:
        return None
    geo = item.get("geolocation") if isinstance(item.get("geolocation"), dict) else {}
    signal = item.get("signal_parametric_data") if isinstance(item.get("signal_parametric_data"), dict) else {}
    emitter = item.get("emitter_identification") if isinstance(item.get("emitter_identification"), dict) else {}
    platform = item.get("correlated_platform") if isinstance(item.get("correlated_platform"), dict) else {}
    ais = platform.get("automatic_identification_system")
    ais = ais if isinstance(ais, dict) else {}
    elnot = _elnot(_first(emitter, "matched_elnot") or _first(item, "ELINT_NOTATION", "elint_notation"))
    mmsi = _text(ais.get("mmsi"))
    platform_confidence = _text(_first(item, "PLATFORM_CONFIDENCE", "platform_confidence"))
    vessel_name = _text(ais.get("name")) or _probable_platform(platform_confidence)
    frequency = _number(_first(signal, "frequency_mhz") or _first(item, "FREQUENCY_MHZ", "frequency_mhz"))
    return {
        "time": observed,
        "value": frequency,
        "channel": elnot or "elint",
        "latitude": _number(_first(geo, "latitude") or _first(item, "LATITUDE", "latitude")),
        "longitude": _number(_first(geo, "longitude") or _first(item, "LONGITUDE", "longitude")),
        "source_id": mmsi or elnot or "elint",
        "details": {
            "intercept_id": _text(_first(item, "intercept_id", "INTERCEPT_ID")),
            "emitter_status": _text(item.get("emitter_status")),
            "elnot": elnot,
            "functional_class": _text(
                _first(emitter, "functional_class") or _first(item, "EMITTER_CLASS", "emitter_class")
            ),
            "frequency_band": _text(emitter.get("frequency_band")),
            "confidence": _number(emitter.get("confidence_score")),
            "platform_confidence": platform_confidence,
            "frequency_mhz": frequency,
            "frequency_modulation": _text(signal.get("frequency_modulation")),
            "pulse_repetition_frequency_hz": _number(signal.get("pulse_repetition_frequency_hz")),
            "pulse_repetition_interval_us": _number(_first(item, "PRI_MICROS", "pri_micros")),
            "pulse_width_us": _number(
                _first(signal, "pulse_width_us") or _first(item, "PULSE_WIDTH_MICROS", "pulse_width_micros")
            ),
            "antenna_scan_type": _text(
                _first(signal, "antenna_scan_type") or _first(item, "SCAN_TYPE", "scan_type")
            ),
            "antenna_scan_period_sec": _number(signal.get("antenna_scan_period_sec")),
            "scan_rate_rpm": _number(_first(item, "SCAN_RATE_RPM", "scan_rate_rpm")),
            "polarization": _text(signal.get("polarization")),
            "snr_db": _number(signal.get("signal_to_noise_ratio_db")),
            "signal_strength_dbm": _number(_first(item, "SIGNAL_STRENGTH_DBM", "signal_strength_dbm")),
            "lob_deg": _number(_first(item, "LOB_DEG", "lob_deg")),
            "platform_type": _text(platform.get("platform_type")),
            "mmsi": mmsi,
            "vessel_name": vessel_name,
            "imo": _text(ais.get("imo")),
            "heading_deg": _number(ais.get("heading_deg")),
            "ellipse_semi_major_axis_m": _number(geo.get("ellipse_semi_major_axis_m")),
            "ellipse_semi_minor_axis_m": _number(geo.get("ellipse_semi_minor_axis_m")),
            "ellipse_orientation_deg": _number(geo.get("ellipse_orientation_deg")),
            "altitude_m": _number(geo.get("altitude_m")),
        },
    }


def _first(item: dict, *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _timestamp(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    for suffix in (" GMT", " UTC"):
        if text.upper().endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def _elnot(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    if text.upper().startswith("ELNOT "):
        return text.split(None, 1)[1].strip() or None
    return text


def _probable_platform(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    for prefix in ("PROBABLE_", "POSSIBLE_", "CONFIRMED_"):
        if text.upper().startswith(prefix):
            text = text[len(prefix) :]
            break
    name = text.replace("_", " ").strip()
    return name or None


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
