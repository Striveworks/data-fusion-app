from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.ingest import router as ingest_router
from app.api.insights import router as insights_router
from app.api.jobs import router as jobs_router
from app.dashboard import router as dashboard_router
from app.db import postgres_session, timescale_session
from app.mcp_server import build_mcp

mcp = build_mcp()


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with mcp.session_manager.run():
        yield


def create_app() -> FastAPI:
    app = FastAPI(title="Data Fusion", lifespan=lifespan)
    app.include_router(dashboard_router)
    app.include_router(ingest_router)
    app.include_router(insights_router)
    app.include_router(jobs_router)
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    @app.get("/health")
    def health() -> dict:
        with postgres_session() as session:
            session.execute(text("SELECT 1"))
        with timescale_session() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok"}

    mcp_app = mcp.streamable_http_app()
    # The mounted app also tries to start the session manager. Only the parent
    # lifespan should do that; run() can be entered once.
    mcp_app.router.lifespan_context = _noop_lifespan
    app.mount("/mcp", mcp_app)
    return app


app = create_app()
