from app.processors.ais import process_ais
from app.processors.fmv import process_fmv
from app.processors.fusion import process_fusion
from app.processors.imagery import JobContext, process_imagery
from app.processors.intel import process_intel
from app.processors.osint import process_osint
from app.processors.ownership import process_ownership
from app.processors.timeseries import process_timeseries
from app.processors.watchpoint import process_watchpoint

HANDLERS = {
    "process_imagery": process_imagery,
    "sync_watchpoint": process_watchpoint,
    "sync_fmv": process_fmv,
    "ingest_timeseries": process_timeseries,
    "ingest_ais": process_ais,
    "ingest_ownership": process_ownership,
    "ingest_osint": process_osint,
    "ingest_intel": process_intel,
    "run_fusion": process_fusion,
}


def dispatch(kind: str, ctx: JobContext) -> dict:
    handler = HANDLERS.get(kind)
    if handler is None:
        raise RuntimeError(f"Unknown job kind {kind}")
    return handler(ctx)
