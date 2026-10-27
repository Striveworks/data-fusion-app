from sqlalchemy import insert

from app.ais import parse_ais_document
from app.models import AisReport
from app.processors.imagery import JobContext
from app.timeutil import parse_time


def process_ais(ctx: JobContext) -> dict:
    inbox_key = ctx.payload.get("inbox_key")
    if inbox_key:
        parsed = parse_ais_document(ctx.store.get(inbox_key))
        reports = parsed.reports
        skipped = parsed.skipped
        skip_reasons = parsed.skip_reasons
    else:
        # Keep old queued jobs compatible while moving new uploads out of job JSON.
        reports = list(ctx.payload.get("reports") or [])
        skipped = ctx.payload.get("skipped") or 0
        skip_reasons = ctx.payload.get("skip_reasons") or {}
    if not reports:
        raise ValueError("AIS ingest requires reports")

    rows: list[dict] = []
    mmsis: set[str] = set()
    vessel_names: set[str] = set()
    destinations: set[str] = set()
    times = []
    for report in reports:
        observed = parse_time(report.get("observed_at"))
        if observed is None:
            raise ValueError("Each AIS report needs a timestamp")
        mmsi = str(report["mmsi"])
        rows.append(
            {
                "mmsi": mmsi,
                "vessel_name": report.get("vessel_name"),
                "call_sign": report.get("call_sign"),
                "imo": report.get("imo"),
                "vessel_type": report.get("vessel_type"),
                "vessel_type_cargo": report.get("vessel_type_cargo"),
                "length": report.get("length"),
                "width": report.get("width"),
                "draft": report.get("draft"),
                "observed_at": observed,
                "latitude": report.get("latitude"),
                "longitude": report.get("longitude"),
                "speed_over_ground_knots": report.get("speed_over_ground_knots"),
                "course_over_ground_degrees": report.get("course_over_ground_degrees"),
                "heading_degrees": report.get("heading_degrees"),
                "navigational_status_code": report.get("navigational_status_code"),
                "navigational_status": report.get("navigational_status"),
                "destination": report.get("destination"),
                "eta": report.get("eta"),
                "details": report.get("details") or {},
            }
        )
        mmsis.add(mmsi)
        if report.get("vessel_name"):
            vessel_names.add(report["vessel_name"])
        if report.get("destination"):
            destinations.add(report["destination"])
        times.append(observed)

    for start in range(0, len(rows), 1000):
        ctx.session.execute(insert(AisReport), rows[start : start + 1000])
    ctx.session.commit()
    if inbox_key:
        ctx.store.delete(inbox_key)

    evidence = {
        "report_count": len(rows),
        "skipped": skipped,
        "skip_reasons": skip_reasons,
        "distinct_mmsis": len(mmsis),
        "distinct_vessel_names": len(vessel_names),
        "distinct_destinations": len(destinations),
        "time_start": min(times).isoformat(),
        "time_end": max(times).isoformat(),
        "storage": "metadata.ais_reports",
    }
    if len(rows) <= 100:
        evidence.update(
            {
                "sample_mmsis": _sample(mmsis),
                "sample_vessel_names": _sample(vessel_names),
                "sample_destinations": _sample(destinations),
            }
        )
    if len(rows) <= 25:
        evidence["observations"] = [_observation(row) for row in rows]
    return {"evidence": evidence}


def _observation(row: dict) -> dict:
    return {
        "mmsi": row["mmsi"],
        "vessel_name": row.get("vessel_name"),
        "call_sign": row.get("call_sign"),
        "imo": row.get("imo"),
        "vessel_type": row.get("vessel_type"),
        "observed_at": row["observed_at"].isoformat(),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "speed_over_ground_knots": row.get("speed_over_ground_knots"),
        "course_over_ground_degrees": row.get("course_over_ground_degrees"),
        "heading_degrees": row.get("heading_degrees"),
        "navigational_status": row.get("navigational_status"),
        "destination": row.get("destination"),
        "eta": row.get("eta"),
    }


def _sample(values, limit: int = 10) -> list[str]:
    return sorted({value for value in values if value})[:limit]
