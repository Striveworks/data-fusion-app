import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import postgres_session, reset_engines, timescale_session


def _can_connect(url: str) -> bool:
    from sqlalchemy import create_engine

    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def settings():
    get_settings.cache_clear()
    reset_engines()
    current = get_settings()
    if not _can_connect(current.postgres_url) or not _can_connect(current.timescale_url):
        pytest.skip("Postgres and TimescaleDB are not reachable")
    return current


@pytest.fixture
def databases(settings):
    with postgres_session(settings) as session:
        session.execute(
            text(
                """
                TRUNCATE
                    metadata.knowledge_graph,
                    metadata.detections,
                    metadata.triage_events,
                    metadata.assets,
                    metadata.ais_reports,
                    metadata.vessel_ownership,
                    metadata.osint_reports,
                    metadata.intel_reports,
                    metadata.jobs
                RESTART IDENTITY CASCADE
                """
            )
        )
        session.commit()
    with timescale_session(settings) as session:
        session.execute(text("TRUNCATE signal_samples"))
        session.commit()
    yield settings
    reset_engines()
