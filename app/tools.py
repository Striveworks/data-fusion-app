"""MCP-callable operations. The HTTP server wraps these functions."""

import json
import uuid

from app.config import Settings, get_settings
from app.corroboration import search_source
from app.db import postgres_session, timescale_session
from app.geo import haversine_meters
from app.knowledge import correct_insight, search_insights, statement_dict, upsert_insight
from app.queries import (
    pattern_counts,
    query_signals,
    search_ais,
    search_assets,
    search_detections,
    search_triage_events,
)
from app.storage import MinioStore, ObjectStore
from app.tracks import associate_tracks


def _split_labels(value) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return [str(value).strip()]


def _json_object(value, *, promote_record: bool = False) -> dict:
    if value is None or value == "" or value == "{}":
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        objects = [item for item in value if isinstance(item, dict)]
        if promote_record and len(objects) == 1 and any(
            key in objects[0] for key in ("subject", "summary", "vessel_name", "name", "entity")
        ):
            return dict(objects[0])
        return {"records": value}
    if not isinstance(value, str):
        raise ValueError("Insight JSON arguments must be an object or a JSON object string")
    text = value.strip()
    if not text or text == "{}":
        return {}
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        if text[:1] in "{[":
            raise ValueError(f"Insight JSON is invalid: {exc.msg}") from exc
        return {"summary": text}
    if isinstance(loaded, str):
        return _json_object(loaded, promote_record=promote_record)
    if isinstance(loaded, dict):
        return loaded
    if isinstance(loaded, list):
        return _json_object(loaded, promote_record=promote_record)
    raise ValueError("Insight JSON must be an object")


def _optional_float(value):
    if value is None or value == "":
        return None
    return float(value)


def _optional_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_insight_args(
    *,
    subject="",
    summary="",
    entity_labels=None,
    place_name="",
    latitude=None,
    longitude=None,
    time_start="",
    time_end="",
    confidence=None,
    evidence_json=None,
    details_json=None,
    require_subject: bool = True,
) -> dict:
    """Accept either top-level insight fields or one JSON object stuffed into details_json."""
    details = _json_object(details_json, promote_record=True)
    evidence = _json_object(evidence_json)
    nested_evidence = details.pop("evidence", None)
    if nested_evidence is None:
        nested_evidence = details.pop("evidence_json", None)
    if not evidence:
        evidence = _json_object(nested_evidence)
    nested_details = details.pop("details", None)
    if nested_details is None:
        nested_details = details.pop("details_json", None)
    if nested_details is not None:
        for key, value in _json_object(nested_details).items():
            details.setdefault(key, value)

    def take(name, explicit):
        if explicit not in (None, ""):
            details.pop(name, None)
            return explicit
        return details.pop(name, None)

    resolved_subject = take("subject", subject)
    if not _optional_text(resolved_subject):
        for alias in ("vessel_name", "name", "entity"):
            resolved_subject = details.pop(alias, None)
            if _optional_text(resolved_subject):
                break
    resolved_subject = _optional_text(resolved_subject)
    if not resolved_subject and require_subject:
        raise ValueError("subject is required. Pass the vessel, place, or entity as the subject argument.")

    labels = take("entity_labels", entity_labels)
    return {
        "subject": resolved_subject,
        "summary": _optional_text(take("summary", summary)),
        "entity_labels": _split_labels(labels),
        "place_name": _optional_text(take("place_name", place_name)),
        "latitude": _optional_float(take("latitude", latitude)),
        "longitude": _optional_float(take("longitude", longitude)),
        "time_start": _optional_text(take("time_start", time_start)),
        "time_end": _optional_text(take("time_end", time_end)),
        "confidence": _optional_float(take("confidence", confidence)),
        "evidence": evidence,
        "object_data": details,
    }


def search_assets_tool(modality: str = "", source_kind: str = "", limit: int = 50) -> list[dict]:
    """List stored imagery and FMV assets, including object-store keys and metadata."""
    with postgres_session() as session:
        return search_assets(
            session,
            modality=modality or None,
            source_kind=source_kind or None,
            limit=limit,
        )


def search_detections_tool(
    label: str = "",
    time_start: str = "",
    time_end: str = "",
    track_id: str = "",
    limit: int = 100,
) -> list[dict]:
    """Search detections produced from imagery, watch points, or FMV inferences."""
    with postgres_session() as session:
        return search_detections(
            session,
            label=label or None,
            time_start=time_start or None,
            time_end=time_end or None,
            track_id=track_id or None,
            limit=limit,
        )


def search_triage_events_tool(watchpoint_id: str = "", limit: int = 50) -> list[dict]:
    """List triage events synced from a Chariot watch point."""
    with postgres_session() as session:
        return search_triage_events(session, watchpoint_id=watchpoint_id or None, limit=limit)


def query_timeseries_tool(
    modality: str = "",
    source_id: str = "",
    mmsi: str = "",
    vessel_name: str = "",
    imo: str = "",
    time_start: str = "",
    time_end: str = "",
    limit: int = 50,
) -> list[dict]:
    """Query radar, ELINT, or acoustic samples. ELINT source_id is the correlated MMSI and channel is the ELNOT."""
    limit = max(1, min(limit, 50))
    with timescale_session() as session:
        return query_signals(
            session,
            modality=modality or None,
            source_id=source_id or None,
            mmsi=mmsi or None,
            vessel_name=vessel_name or None,
            imo=imo or None,
            time_start=time_start or None,
            time_end=time_end or None,
            limit=limit,
        )


def search_ais_tool(
    mmsi: str = "",
    vessel_name: str = "",
    call_sign: str = "",
    imo: str = "",
    destination: str = "",
    time_start: str = "",
    time_end: str = "",
    limit: int = 25,
) -> list[dict]:
    """Search stored Automatic Identification System reports by vessel identity, destination, or time."""
    with postgres_session() as session:
        return search_ais(
            session,
            mmsi=mmsi or None,
            vessel_name=vessel_name or None,
            call_sign=call_sign or None,
            imo=imo or None,
            destination=destination or None,
            time_start=time_start or None,
            time_end=time_end or None,
            limit=limit,
        )


def measure_distance_tool(lat1: float, lon1: float, lat2: float, lon2: float) -> dict:
    """Measure the great-circle distance in meters between two coordinates."""
    return {"meters": haversine_meters(lat1, lon1, lat2, lon2)}


def associate_tracks_tool(
    label: str = "",
    time_start: str = "",
    time_end: str = "",
    max_meters: float = 500,
    max_seconds: float = 300,
) -> dict:
    """Cluster nearby detections into tracks and persist the track id on each detection."""
    with postgres_session() as session:
        result = associate_tracks(
            session,
            label=label or None,
            time_start=time_start or None,
            time_end=time_end or None,
            max_meters=max_meters,
            max_seconds=max_seconds,
        )
        session.commit()
        return result


def pattern_of_life_tool(
    place_name: str = "",
    label: str = "",
    modality: str = "",
    time_start: str = "",
    time_end: str = "",
) -> dict:
    """Count detections, signal samples, and AIS reports by label, modality, vessel, and source."""
    with postgres_session() as session, timescale_session() as timescale:
        return pattern_counts(
            session,
            timescale,
            place_name=place_name or None,
            label=label or None,
            modality=modality or None,
            time_start=time_start or None,
            time_end=time_end or None,
        )


def search_insights_tool(
    entity: str = "",
    place: str = "",
    time_start: str = "",
    time_end: str = "",
    limit: int = 50,
) -> list[dict]:
    """Search active fused insights by entity, place, or time range."""
    with postgres_session() as session:
        rows = search_insights(
            session,
            entity=entity or None,
            place=place or None,
            time_start=time_start or None,
            time_end=time_end or None,
            limit=limit,
        )
        return [statement_dict(row) for row in rows]


def upsert_insight_tool(
    subject: str = "",
    summary: str = "",
    entity_labels: str | list | None = None,
    place_name: str = "",
    latitude: float | str | None = None,
    longitude: float | str | None = None,
    time_start: str = "",
    time_end: str = "",
    confidence: float | str | None = None,
    evidence_json: str | dict | list | None = None,
    details_json: str | dict | list | None = None,
) -> dict:
    """Write a new active insight. Pass subject as its own argument, not only inside details_json."""
    fields = normalize_insight_args(
        subject=subject,
        summary=summary,
        entity_labels=entity_labels,
        place_name=place_name,
        latitude=latitude,
        longitude=longitude,
        time_start=time_start,
        time_end=time_end,
        confidence=confidence,
        evidence_json=evidence_json,
        details_json=details_json,
    )
    with postgres_session() as session:
        row = upsert_insight(session, **fields)
        session.commit()
        return statement_dict(row)


def correct_insight_tool(
    insight_id: str,
    subject: str = "",
    summary: str = "",
    entity_labels: str | list | None = None,
    place_name: str = "",
    latitude: float | str | None = None,
    longitude: float | str | None = None,
    time_start: str = "",
    time_end: str = "",
    confidence: float | str | None = None,
    evidence_json: str | dict | list | None = None,
    details_json: str | dict | list | None = None,
) -> dict:
    """Supersede an active insight with a corrected statement. The previous row is kept."""
    raw_details = _json_object(details_json, promote_record=True)
    fields = normalize_insight_args(
        subject=subject,
        summary=summary,
        entity_labels=entity_labels,
        place_name=place_name,
        latitude=latitude,
        longitude=longitude,
        time_start=time_start,
        time_end=time_end,
        confidence=confidence,
        evidence_json=evidence_json,
        details_json=details_json,
        require_subject=False,
    )
    supplied_subject = bool(subject) or any(raw_details.get(key) for key in ("subject", "vessel_name", "name", "entity"))
    if not supplied_subject:
        fields["subject"] = None
    if not summary and "summary" not in raw_details:
        fields["summary"] = None
    if entity_labels in (None, "", []) and "entity_labels" not in raw_details:
        fields["entity_labels"] = None
    if not place_name and "place_name" not in raw_details:
        fields["place_name"] = None
    if latitude in (None, "") and "latitude" not in raw_details:
        fields["latitude"] = None
    if longitude in (None, "") and "longitude" not in raw_details:
        fields["longitude"] = None
    if not time_start and "time_start" not in raw_details:
        fields["time_start"] = None
    if not time_end and "time_end" not in raw_details:
        fields["time_end"] = None
    if confidence in (None, "") and "confidence" not in raw_details:
        fields["confidence"] = None
    if not evidence_json and "evidence" not in raw_details and "evidence_json" not in raw_details:
        fields["evidence"] = None
    if not fields["object_data"]:
        fields["object_data"] = None
    with postgres_session() as session:
        row = correct_insight(session, uuid.UUID(insight_id), **fields)
        session.commit()
        return statement_dict(row)


def describe_imagery_tool(asset_id: str, prompt: str = "Describe the objects and activity in this image.") -> dict:
    """Describe a stored image with the configured Chariot vision model."""
    settings = get_settings()
    if not settings.chariot_vlm_model_id:
        return {
            "status": "unconfigured",
            "results": [],
            "detail": "CHARIOT_VLM_MODEL_ID is unset",
        }
    from app.chariot import ChariotGateway
    from app.models import Asset

    with postgres_session() as session:
        asset = session.get(Asset, uuid.UUID(asset_id))
        if asset is None or not asset.object_key:
            raise LookupError(f"Asset {asset_id} was not found")
        object_key = asset.object_key
    data = _store(settings).get(object_key)
    from app.chariot import DescriptionUnsupported

    try:
        description = ChariotGateway(settings).describe_image(settings.chariot_vlm_model_id, data, prompt)
    except DescriptionUnsupported as exc:
        return {"status": "unavailable", "results": [], "detail": str(exc)}
    return {"status": "ok", "results": [{"asset_id": asset_id, "description": description}]}


def search_intel_reports_tool(query: str) -> dict:
    """Search stored intel reports by person, vessel, IMO, status, or report text."""
    return search_source("intel_reports", query)


def search_ownership_tool(query: str) -> dict:
    """Search stored vessel ownership records by name, IMO, MMSI, call sign, flag, or sanctions."""
    return search_source("ownership", query)


def search_osint_tool(query: str) -> dict:
    """Search stored OSINT reports by vessel, IMO, MMSI, place, event, or report text."""
    return search_source("osint", query)


def _store(settings: Settings) -> ObjectStore:
    return MinioStore(
        settings.minio_endpoint,
        settings.minio_access_key,
        settings.minio_secret_key,
        settings.minio_bucket,
        settings.minio_secure,
    )
