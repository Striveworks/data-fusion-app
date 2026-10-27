import uuid

from app.chariot import suffix_for
from app.elint import parse_elint_document
from app.models import SignalSample
from app.processors.imagery import JobContext
from app.timeutil import parse_time


def process_timeseries(ctx: JobContext) -> dict:
    payload = ctx.payload
    object_key = None
    inbox_key = payload.get("inbox_key")
    inbox_data = None
    if inbox_key:
        inbox_data = ctx.store.get(inbox_key)
        suffix = suffix_for(payload.get("content_type"), payload.get("filename"))
        object_key = f"signals/{uuid.uuid4()}{suffix}"
        ctx.store.put(object_key, inbox_data, payload.get("content_type") or "application/octet-stream")
        ctx.store.delete(inbox_key)

    samples = list(payload.get("samples") or [])
    if inbox_data is not None and not samples:
        samples = parse_elint_document(inbox_data)
    if object_key and not samples:
        samples = [
            {
                "time": payload.get("captured_at"),
                "value": None,
                "channel": "file",
                "latitude": payload.get("latitude"),
                "longitude": payload.get("longitude"),
            }
        ]
    if not samples:
        raise ValueError("Time series ingest requires samples or an ELINT intercept file")

    default_source = payload.get("source_id") or "elint"
    modality = payload["modality"]
    source_ids: list[str] = []
    times = []
    for sample in samples:
        observed = parse_time(sample.get("time") or payload.get("captured_at"))
        if observed is None:
            raise ValueError("Each time series sample needs a time")
        source_id = sample.get("source_id") or default_source
        ctx.timescale.add(
            SignalSample(
                time=observed,
                modality=modality,
                source_id=source_id,
                channel=sample.get("channel") or "default",
                value=sample.get("value"),
                latitude=sample.get("latitude", payload.get("latitude")),
                longitude=sample.get("longitude", payload.get("longitude")),
                details=sample.get("details") or {},
                object_key=object_key,
            )
        )
        if source_id not in source_ids:
            source_ids.append(source_id)
        times.append(observed)
    ctx.timescale.commit()
    return {"evidence": _evidence(modality, samples, source_ids, times)}


def _evidence(modality: str, samples: list[dict], source_ids: list[str], times: list) -> dict:
    evidence = {
        "storage": "signal_samples",
        "modality": modality,
        "signal_source_ids": source_ids,
        "sample_count": len(samples),
        "time_start": min(times).isoformat(),
        "time_end": max(times).isoformat(),
    }
    if modality != "elint":
        return evidence
    names = sorted({_detail(sample, "vessel_name") for sample in samples if _detail(sample, "vessel_name")})
    mmsis = sorted({_detail(sample, "mmsi") for sample in samples if _detail(sample, "mmsi")})
    imos = sorted({_detail(sample, "imo") for sample in samples if _detail(sample, "imo")})
    elnots = sorted({_detail(sample, "elnot") for sample in samples if _detail(sample, "elnot")})
    evidence.update(
        {
            "sample_vessel_names": names,
            "sample_mmsis": mmsis,
            "sample_imos": imos,
            "elnots": elnots,
        }
    )
    if len(samples) <= 25:
        evidence["intercepts"] = [_intercept(sample) for sample in samples]
    return evidence


def _detail(sample: dict, key: str) -> str | None:
    value = (sample.get("details") or {}).get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _intercept(sample: dict) -> dict:
    details = sample.get("details") or {}
    return {
        "intercept_id": details.get("intercept_id"),
        "time": sample.get("time"),
        "latitude": sample.get("latitude"),
        "longitude": sample.get("longitude"),
        "elnot": details.get("elnot"),
        "frequency_band": details.get("frequency_band"),
        "frequency_mhz": details.get("frequency_mhz"),
        "confidence": details.get("confidence"),
        "vessel_name": details.get("vessel_name"),
        "mmsi": details.get("mmsi"),
        "imo": details.get("imo"),
        "heading_deg": details.get("heading_deg"),
    }
