from fastapi import APIRouter, HTTPException, Query

from app.corroboration import probe_sources
from app.db import postgres_session
from app.knowledge import get_statement, search_insights, statement_dict

router = APIRouter(prefix="/api/v1", tags=["insights"])


@router.get("/insights")
def list_insights(
    entity: str | None = None,
    place: str | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    limit: int = Query(default=100, le=500),
) -> list[dict]:
    with postgres_session() as session:
        rows = search_insights(
            session,
            entity=entity,
            place=place,
            time_start=time_start,
            time_end=time_end,
            limit=limit,
        )
        return [statement_dict(row) for row in rows]


@router.get("/insights/{insight_id}")
def read_insight(insight_id: str) -> dict:
    import uuid

    try:
        parsed = uuid.UUID(insight_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Insight not found") from exc
    with postgres_session() as session:
        row = get_statement(session, parsed)
        if row is None:
            raise HTTPException(status_code=404, detail="Insight not found")
        return statement_dict(row)


@router.get("/corroboration")
def corroboration(query: str = "") -> list[dict]:
    return probe_sources(query)
