"""Read-side queries used by the API, dashboard, and MCP tools."""

from datetime import datetime

from sqlalchemy import func, nulls_last, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AisReport,
    Asset,
    Detection,
    IntelReport,
    OsintReport,
    SignalSample,
    TriageEvent,
    VesselOwnership,
)
from app.timeutil import parse_time


def _window(query, column, start, end):
    parsed_start = parse_time(start)
    parsed_end = parse_time(end)
    if parsed_start is not None:
        query = query.where(column >= parsed_start)
    if parsed_end is not None:
        query = query.where(column <= parsed_end)
    return query


def search_assets(
    session: Session,
    *,
    modality: str | None = None,
    source_kind: str | None = None,
    limit: int = 50,
) -> list[dict]:
    query = select(Asset).order_by(Asset.created_at.desc()).limit(limit)
    if modality:
        query = query.where(Asset.modality == modality)
    if source_kind:
        query = query.where(Asset.source_kind == source_kind)
    rows = session.scalars(query)
    return [
        {
            "id": str(row.id),
            "modality": row.modality,
            "captured_at": row.captured_at.isoformat() if row.captured_at else None,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "object_key": row.object_key,
            "source_kind": row.source_kind,
            "external_id": row.external_id,
            "details": row.details or {},
        }
        for row in rows
    ]


def search_detections(
    session: Session,
    *,
    label: str | None = None,
    time_start: datetime | str | None = None,
    time_end: datetime | str | None = None,
    track_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    query = select(Detection).order_by(nulls_last(Detection.observed_at.desc()), Detection.created_at.desc())
    if label:
        query = query.where(Detection.label.ilike(f"%{label}%"))
    if track_id:
        query = query.where(Detection.track_id == track_id)
    query = _window(query, func.coalesce(Detection.observed_at, Detection.created_at), time_start, time_end)
    query = query.limit(limit)
    return [
        {
            "id": str(row.id),
            "asset_id": str(row.asset_id) if row.asset_id else None,
            "triage_event_id": str(row.triage_event_id) if row.triage_event_id else None,
            "label": row.label,
            "score": row.score,
            "geometry": row.geometry,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "chariot_inference_id": row.chariot_inference_id,
            "model_id": row.model_id,
            "track_id": row.track_id,
            "observed_at": row.observed_at.isoformat() if row.observed_at else None,
            "attributes": row.attributes or {},
        }
        for row in session.scalars(query)
    ]


def search_triage_events(
    session: Session,
    *,
    watchpoint_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    query = select(TriageEvent).order_by(nulls_last(TriageEvent.captured_at.desc())).limit(limit)
    if watchpoint_id:
        query = query.where(TriageEvent.watchpoint_id == watchpoint_id)
    return [
        {
            "id": str(row.id),
            "watchpoint_id": row.watchpoint_id,
            "chariot_event_id": row.chariot_event_id,
            "review_status": row.review_status,
            "captured_at": row.captured_at.isoformat() if row.captured_at else None,
            "chariot_ids": row.chariot_ids or {},
            "details": row.details or {},
        }
        for row in session.scalars(query)
    ]


def query_signals(
    session: Session,
    *,
    modality: str | None = None,
    source_id: str | None = None,
    mmsi: str | None = None,
    vessel_name: str | None = None,
    imo: str | None = None,
    time_start: datetime | str | None = None,
    time_end: datetime | str | None = None,
    limit: int = 200,
) -> list[dict]:
    query = select(SignalSample).order_by(SignalSample.time.desc())
    if modality:
        query = query.where(SignalSample.modality == modality)
    if source_id:
        query = query.where(SignalSample.source_id == source_id)
    if mmsi:
        query = query.where(SignalSample.details["mmsi"].astext == str(mmsi).strip())
    if vessel_name:
        query = query.where(SignalSample.details["vessel_name"].astext.ilike(f"%{vessel_name.strip()}%"))
    if imo:
        query = query.where(SignalSample.details["imo"].astext == str(imo).strip())
    query = _window(query, SignalSample.time, time_start, time_end).limit(limit)
    rows = []
    for row in session.scalars(query):
        details = row.details or {}
        rows.append(
            {
                "id": str(row.id),
                "time": row.time.isoformat(),
                "modality": row.modality,
                "source_id": row.source_id,
                "channel": row.channel,
                "value": row.value,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "object_key": row.object_key,
                "intercept_id": details.get("intercept_id"),
                "elnot": details.get("elnot"),
                "frequency_band": details.get("frequency_band"),
                "vessel_name": details.get("vessel_name"),
                "mmsi": details.get("mmsi"),
                "imo": details.get("imo"),
                "details": details,
            }
        )
    return rows


def search_ais(
    session: Session,
    *,
    mmsi: str | None = None,
    vessel_name: str | None = None,
    call_sign: str | None = None,
    imo: str | None = None,
    destination: str | None = None,
    time_start: datetime | str | None = None,
    time_end: datetime | str | None = None,
    limit: int = 25,
) -> list[dict]:
    limit = max(1, min(limit, 50))
    query = select(AisReport).order_by(AisReport.observed_at.desc())
    if mmsi:
        query = query.where(AisReport.mmsi == str(mmsi).strip())
    if vessel_name:
        query = query.where(AisReport.vessel_name.ilike(f"%{vessel_name}%"))
    if call_sign:
        query = query.where(AisReport.call_sign.ilike(call_sign.strip()))
    if imo:
        query = query.where(AisReport.imo == str(imo).strip())
    if destination:
        query = query.where(AisReport.destination.ilike(f"%{destination}%"))
    query = _window(query, AisReport.observed_at, time_start, time_end).limit(limit)
    return [_ais_dict(row) for row in session.scalars(query)]


def _ais_dict(row: AisReport) -> dict:
    return {
        "id": str(row.id),
        "mmsi": row.mmsi,
        "vessel_name": row.vessel_name,
        "call_sign": row.call_sign,
        "imo": row.imo,
        "vessel_type": row.vessel_type,
        "vessel_type_cargo": row.vessel_type_cargo,
        "length": row.length,
        "width": row.width,
        "draft": row.draft,
        "timestamp": row.observed_at.isoformat(),
        "latitude": row.latitude,
        "longitude": row.longitude,
        "speed_over_ground_knots": row.speed_over_ground_knots,
        "course_over_ground_degrees": row.course_over_ground_degrees,
        "heading_degrees": row.heading_degrees,
        "navigational_status_code": row.navigational_status_code,
        "navigational_status": row.navigational_status,
        "destination": row.destination,
        "eta": row.eta,
        "details": row.details or {},
    }


def search_vessel_ownership(session: Session, query: str, limit: int = 25) -> dict:
    text = (query or "").strip()
    count_query = select(func.count()).select_from(VesselOwnership)
    if text:
        pattern = f"%{text}%"
        matched = or_(
            VesselOwnership.vessel_name.ilike(pattern),
            VesselOwnership.imo.ilike(pattern),
            VesselOwnership.mmsi.ilike(pattern),
            VesselOwnership.call_sign.ilike(pattern),
            VesselOwnership.flag_current.ilike(pattern),
            VesselOwnership.vessel_type.ilike(pattern),
            VesselOwnership.sanctions.ilike(pattern),
            VesselOwnership.category.ilike(pattern),
            VesselOwnership.sanctions_person.ilike(pattern),
        )
        count_query = count_query.where(matched)
        rows = session.scalars(
            select(VesselOwnership).where(matched).order_by(VesselOwnership.vessel_name).limit(limit)
        )
        results = [_ownership_dict(row) for row in rows]
    else:
        results = []
    count = session.scalar(count_query) or 0
    return {"source": "ownership", "status": "ok", "query": query, "count": count, "results": results}


def _ownership_dict(row: VesselOwnership) -> dict:
    return {
        "id": str(row.id),
        "dataset": row.dataset,
        "vessel_name": row.vessel_name,
        "category": row.category,
        "imo": row.imo,
        "flag_current": row.flag_current,
        "mmsi": row.mmsi,
        "call_sign": row.call_sign,
        "vessel_type": row.vessel_type,
        "length_m": row.length_m,
        "gross_tonnage": row.gross_tonnage,
        "dwt": row.dwt,
        "sanctions": row.sanctions,
        "sanction_links": row.sanction_links or [],
        "sanctions_person": row.sanctions_person,
        "source_url": row.source_url,
    }


def search_osint(session: Session, query: str, limit: int = 25) -> dict:
    text = (query or "").strip()
    count_query = select(func.count()).select_from(OsintReport)
    if text:
        pattern = f"%{text}%"
        matched = or_(
            OsintReport.title.ilike(pattern),
            OsintReport.vessel_name.ilike(pattern),
            OsintReport.imo.ilike(pattern),
            OsintReport.mmsi.ilike(pattern),
            OsintReport.flag.ilike(pattern),
            OsintReport.vessel_type.ilike(pattern),
            OsintReport.event.ilike(pattern),
            OsintReport.origin.ilike(pattern),
            OsintReport.destination.ilike(pattern),
            OsintReport.summary.ilike(pattern),
            OsintReport.body.ilike(pattern),
        )
        count_query = count_query.where(matched)
        rows = session.scalars(
            select(OsintReport).where(matched).order_by(OsintReport.report_date.desc()).limit(limit)
        )
        results = [_osint_dict(row) for row in rows]
    else:
        results = []
    count = session.scalar(count_query) or 0
    return {"source": "osint", "status": "ok", "query": query, "count": count, "results": results}


def _osint_dict(row: OsintReport) -> dict:
    return {
        "id": str(row.id),
        "title": row.title,
        "vessel_name": row.vessel_name,
        "imo": row.imo,
        "mmsi": row.mmsi,
        "flag": row.flag,
        "vessel_type": row.vessel_type,
        "event": row.event,
        "event_date": row.event_date.isoformat() if row.event_date else None,
        "report_date": row.report_date.isoformat() if row.report_date else None,
        "origin": row.origin,
        "destination": row.destination,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "summary": row.summary,
        "body": row.body,
        "source": row.source,
        "details": row.details or {},
    }


def search_intel_reports(session: Session, query: str, limit: int = 25) -> dict:
    text = (query or "").strip()
    count_query = select(func.count()).select_from(IntelReport)
    if text:
        pattern = f"%{text}%"
        matched = or_(
            IntelReport.title.ilike(pattern),
            IntelReport.classification.ilike(pattern),
            IntelReport.subject.ilike(pattern),
            IntelReport.person_name.ilike(pattern),
            IntelReport.vessel_name.ilike(pattern),
            IntelReport.imo.ilike(pattern),
            IntelReport.mmsi.ilike(pattern),
            IntelReport.status.ilike(pattern),
            IntelReport.summary.ilike(pattern),
            IntelReport.body.ilike(pattern),
            IntelReport.source.ilike(pattern),
        )
        count_query = count_query.where(matched)
        rows = session.scalars(
            select(IntelReport)
            .where(matched)
            .order_by(nulls_last(IntelReport.event_date.desc()))
            .limit(limit)
        )
        results = [_intel_dict(row) for row in rows]
    else:
        results = []
    count = session.scalar(count_query) or 0
    return {"source": "intel_reports", "status": "ok", "query": query, "count": count, "results": results}


def _intel_dict(row: IntelReport) -> dict:
    return {
        "id": str(row.id),
        "title": row.title,
        "classification": row.classification,
        "subject": row.subject,
        "person_name": row.person_name,
        "vessel_name": row.vessel_name,
        "imo": row.imo,
        "mmsi": row.mmsi,
        "status": row.status,
        "event_date": row.event_date.isoformat() if row.event_date else None,
        "summary": row.summary,
        "body": row.body,
        "source": row.source,
        "details": row.details or {},
    }


def pattern_counts(
    session: Session,
    timescale: Session,
    *,
    place_name: str | None = None,
    label: str | None = None,
    modality: str | None = None,
    time_start: datetime | str | None = None,
    time_end: datetime | str | None = None,
) -> dict:
    detection_query = select(Detection.label, func.count()).group_by(Detection.label)
    if label:
        detection_query = detection_query.where(Detection.label.ilike(f"%{label}%"))
    detection_query = _window(
        detection_query,
        func.coalesce(Detection.observed_at, Detection.created_at),
        time_start,
        time_end,
    )
    if place_name:
        detection_query = detection_query.where(
            or_(
                Detection.attributes["place_name"].astext.ilike(f"%{place_name}%"),
                Detection.label.ilike(f"%{place_name}%"),
            )
        )
    detections = [
        {"label": item_label, "count": count}
        for item_label, count in session.execute(detection_query)
    ]

    signal_query = select(SignalSample.modality, SignalSample.source_id, func.count()).group_by(
        SignalSample.modality, SignalSample.source_id
    )
    if modality:
        signal_query = signal_query.where(SignalSample.modality == modality)
    signal_query = _window(signal_query, SignalSample.time, time_start, time_end)
    signals = [
        {"modality": item_modality, "source_id": source_id, "count": count}
        for item_modality, source_id, count in timescale.execute(signal_query)
    ]

    ais: dict = {"report_count": 0, "distinct_vessels": 0, "top_vessels": []}
    if not modality or modality == "ais":
        summary_query = select(
            func.count(AisReport.id),
            func.count(func.distinct(AisReport.mmsi)),
        )
        if place_name:
            summary_query = summary_query.where(
                or_(
                    AisReport.destination.ilike(f"%{place_name}%"),
                    AisReport.vessel_name.ilike(f"%{place_name}%"),
                )
            )
        if label:
            summary_query = summary_query.where(
                or_(AisReport.mmsi == label, AisReport.vessel_name.ilike(f"%{label}%"))
            )
        summary_query = _window(summary_query, AisReport.observed_at, time_start, time_end)
        report_count, distinct_vessels = session.execute(summary_query).one()
        ais_query = select(AisReport.mmsi, AisReport.vessel_name, func.count()).group_by(
            AisReport.mmsi, AisReport.vessel_name
        )
        if place_name:
            ais_query = ais_query.where(
                or_(
                    AisReport.destination.ilike(f"%{place_name}%"),
                    AisReport.vessel_name.ilike(f"%{place_name}%"),
                )
            )
        if label:
            ais_query = ais_query.where(
                or_(AisReport.mmsi == label, AisReport.vessel_name.ilike(f"%{label}%"))
            )
        ais_query = _window(ais_query, AisReport.observed_at, time_start, time_end)
        ais_query = ais_query.order_by(func.count().desc()).limit(25)
        ais = {
            "report_count": report_count,
            "distinct_vessels": distinct_vessels,
            "top_vessels": [
                {"mmsi": item_mmsi, "vessel_name": name, "count": count}
                for item_mmsi, name, count in session.execute(ais_query)
            ],
        }
    return {"detections": detections, "signals": signals, "ais": ais}
