import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import KnowledgeStatement
from app.timeutil import parse_time


def _now() -> datetime:
    return datetime.now(timezone.utc)


def statement_dict(row: KnowledgeStatement) -> dict:
    return {
        "id": str(row.id),
        "subject": row.subject,
        "predicate": row.predicate,
        "object": row.object_data or {},
        "summary": row.summary,
        "entity_labels": list(row.entity_labels or []),
        "place_name": row.place_name,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "time_start": row.time_start.isoformat() if row.time_start else None,
        "time_end": row.time_end.isoformat() if row.time_end else None,
        "confidence": row.confidence,
        "status": row.status,
        "supersedes_id": str(row.supersedes_id) if row.supersedes_id else None,
        "evidence": row.evidence or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def search_insights(
    session: Session,
    *,
    entity: str | None = None,
    place: str | None = None,
    time_start: datetime | str | None = None,
    time_end: datetime | str | None = None,
    limit: int = 100,
) -> list[KnowledgeStatement]:
    start = parse_time(time_start)
    end = parse_time(time_end)
    query = select(KnowledgeStatement).where(
        KnowledgeStatement.predicate == "insight",
        KnowledgeStatement.status == "active",
    )
    if entity:
        query = query.where(
            or_(
                KnowledgeStatement.entity_labels.any(entity),
                KnowledgeStatement.subject.ilike(f"%{entity}%"),
                KnowledgeStatement.summary.ilike(f"%{entity}%"),
            )
        )
    if place:
        query = query.where(KnowledgeStatement.place_name.ilike(f"%{place}%"))
    if start is not None:
        query = query.where(
            or_(KnowledgeStatement.time_end.is_(None), KnowledgeStatement.time_end >= start)
        )
    if end is not None:
        query = query.where(
            or_(KnowledgeStatement.time_start.is_(None), KnowledgeStatement.time_start <= end)
        )
    query = query.order_by(KnowledgeStatement.updated_at.desc()).limit(limit)
    return list(session.scalars(query))


def get_statement(session: Session, statement_id: uuid.UUID) -> KnowledgeStatement | None:
    return session.get(KnowledgeStatement, statement_id)


def upsert_insight(
    session: Session,
    *,
    subject: str,
    summary: str | None = None,
    entity_labels: list[str] | None = None,
    place_name: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    time_start: datetime | str | None = None,
    time_end: datetime | str | None = None,
    confidence: float | None = None,
    evidence: dict | None = None,
    object_data: dict | None = None,
) -> KnowledgeStatement:
    row = KnowledgeStatement(
        subject=subject,
        predicate="insight",
        summary=summary,
        entity_labels=entity_labels or [],
        place_name=place_name or None,
        latitude=latitude,
        longitude=longitude,
        time_start=parse_time(time_start),
        time_end=parse_time(time_end),
        confidence=confidence,
        status="active",
        evidence=evidence or {},
        object_data=object_data or {},
        updated_at=_now(),
    )
    session.add(row)
    session.flush()
    return row


def correct_insight(
    session: Session,
    insight_id: uuid.UUID,
    *,
    subject: str | None = None,
    summary: str | None = None,
    entity_labels: list[str] | None = None,
    place_name: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    time_start: datetime | str | None = None,
    time_end: datetime | str | None = None,
    confidence: float | None = None,
    evidence: dict | None = None,
    object_data: dict | None = None,
) -> KnowledgeStatement:
    previous = session.get(KnowledgeStatement, insight_id)
    if previous is None or previous.predicate != "insight":
        raise LookupError(f"Insight {insight_id} was not found")
    if previous.status != "active":
        raise LookupError(f"Insight {insight_id} is {previous.status} and cannot be corrected")

    replacement = KnowledgeStatement(
        subject=subject if subject is not None else previous.subject,
        predicate="insight",
        summary=summary if summary is not None else previous.summary,
        entity_labels=entity_labels if entity_labels is not None else list(previous.entity_labels or []),
        place_name=place_name if place_name is not None else previous.place_name,
        latitude=latitude if latitude is not None else previous.latitude,
        longitude=longitude if longitude is not None else previous.longitude,
        time_start=parse_time(time_start) if time_start is not None else previous.time_start,
        time_end=parse_time(time_end) if time_end is not None else previous.time_end,
        confidence=confidence if confidence is not None else previous.confidence,
        status="active",
        supersedes_id=previous.id,
        evidence=evidence if evidence is not None else dict(previous.evidence or {}),
        object_data=object_data if object_data is not None else dict(previous.object_data or {}),
        updated_at=_now(),
    )
    previous.status = "superseded"
    previous.updated_at = _now()
    session.add(replacement)
    session.flush()
    return replacement
