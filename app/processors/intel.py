from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.models import IntelReport
from app.processors.imagery import JobContext


def process_intel(ctx: JobContext) -> dict:
    reports = list(ctx.payload.get("reports") or [])
    if not reports:
        raise ValueError("Intel ingest requires reports")
    rows = [_row(report) for report in reports]
    table = IntelReport.__table__
    statement = insert(table).values(rows)
    update_columns = {
        column.name: statement.excluded[column.name]
        for column in table.columns
        if column.name not in {"id", "created_at", "updated_at"}
    }
    update_columns["updated_at"] = func.now()
    statement = statement.on_conflict_do_update(
        index_elements=["report_key"],
        set_=update_columns,
    )
    ctx.session.execute(statement)
    ctx.session.commit()
    return {
        "evidence": {
            "storage": "metadata.intel_reports",
            "report_count": len(rows),
            "sample_vessel_names": sorted({row["vessel_name"] for row in rows if row["vessel_name"]}),
            "sample_imos": sorted({row["imo"] for row in rows if row["imo"]}),
            "sample_mmsis": sorted({row["mmsi"] for row in rows if row["mmsi"]}),
            "person_names": sorted({row["person_name"] for row in rows if row["person_name"]}),
            "titles": [row["title"] for row in rows if row["title"]][:25],
        }
    }


def _row(report: dict) -> dict:
    return {
        "report_key": report.get("report_key"),
        "title": report.get("title"),
        "classification": report.get("classification"),
        "subject": report.get("subject"),
        "person_name": report.get("person_name"),
        "vessel_name": report.get("vessel_name"),
        "imo": report.get("imo"),
        "mmsi": report.get("mmsi"),
        "status": report.get("status"),
        "event_date": _date(report.get("event_date")),
        "summary": report.get("summary"),
        "body": report.get("body") or "",
        "source": report.get("source"),
        "details": report.get("details") or {},
    }


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])
