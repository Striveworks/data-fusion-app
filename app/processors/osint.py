from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.models import OsintReport
from app.processors.imagery import JobContext


def process_osint(ctx: JobContext) -> dict:
    reports = list(ctx.payload.get("reports") or [])
    if not reports:
        raise ValueError("OSINT ingest requires reports")
    rows = [_row(report) for report in reports]
    table = OsintReport.__table__
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
    names = sorted({row["vessel_name"] for row in rows if row["vessel_name"]})
    return {
        "evidence": {
            "storage": "metadata.osint_reports",
            "report_count": len(rows),
            "sample_vessel_names": names,
            "sample_imos": sorted({row["imo"] for row in rows if row["imo"]}),
            "sample_mmsis": sorted({row["mmsi"] for row in rows if row["mmsi"]}),
            "titles": [row["title"] for row in rows if row["title"]][:25],
        }
    }


def _row(report: dict) -> dict:
    return {
        "report_key": report.get("report_key"),
        "title": report.get("title"),
        "vessel_name": report.get("vessel_name"),
        "imo": report.get("imo"),
        "mmsi": report.get("mmsi"),
        "flag": report.get("flag"),
        "vessel_type": report.get("vessel_type"),
        "event": report.get("event"),
        "event_date": _date(report.get("event_date")),
        "report_date": _date(report.get("report_date")),
        "origin": report.get("origin"),
        "destination": report.get("destination"),
        "latitude": report.get("latitude"),
        "longitude": report.get("longitude"),
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
