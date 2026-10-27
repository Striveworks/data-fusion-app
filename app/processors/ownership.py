from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.models import VesselOwnership
from app.processors.imagery import JobContext


def process_ownership(ctx: JobContext) -> dict:
    records = list(ctx.payload.get("records") or [])
    if not records:
        raise ValueError("Ownership ingest requires records")
    dataset = ctx.payload.get("dataset") or "vessel_ownership"
    rows = []
    for record in records:
        rows.append(
            {
                "dataset": dataset,
                "vessel_name": record.get("vessel_name"),
                "category": record.get("category"),
                "imo": record.get("imo"),
                "flag_current": record.get("flag_current"),
                "mmsi": record.get("mmsi"),
                "call_sign": record.get("call_sign"),
                "vessel_type": record.get("vessel_type"),
                "length_m": record.get("length_m"),
                "gross_tonnage": record.get("gross_tonnage"),
                "dwt": record.get("dwt"),
                "sanctions": record.get("sanctions"),
                "sanction_links": record.get("sanction_links") or [],
                "sanctions_person": record.get("sanctions_person"),
                "picture_filename": record.get("picture_filename"),
                "source_url": record.get("source_url"),
                "main_photo_url": record.get("main_photo_url"),
                "details": record.get("details") or {},
            }
        )
    table = VesselOwnership.__table__
    statement = insert(table).values(rows)
    update_columns = {
        column.name: statement.excluded[column.name]
        for column in table.columns
        if column.name not in {"id", "created_at", "updated_at"}
    }
    update_columns["updated_at"] = func.now()
    statement = statement.on_conflict_do_update(
        index_elements=["source_url"],
        set_=update_columns,
    )
    ctx.session.execute(statement)
    ctx.session.commit()
    names = _sample(record.get("vessel_name") for record in records)
    return {
        "evidence": {
            "dataset": dataset,
            "record_count": len(records),
            "vessel_names": names,
        }
    }


def _sample(values, limit: int = 25) -> list[str]:
    return sorted({value for value in values if value})[:limit]
