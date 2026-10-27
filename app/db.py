from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings

_engines: dict[str, object] = {}
_sessions: dict[str, sessionmaker] = {}


def _sessionmaker_for(url: str) -> sessionmaker:
    if url not in _sessions:
        engine = create_engine(url, pool_pre_ping=True)
        _engines[url] = engine
        _sessions[url] = sessionmaker(bind=engine, expire_on_commit=False)
    return _sessions[url]


def postgres_sessionmaker(settings: Settings | None = None) -> sessionmaker:
    settings = settings or get_settings()
    return _sessionmaker_for(settings.postgres_url)


def timescale_sessionmaker(settings: Settings | None = None) -> sessionmaker:
    settings = settings or get_settings()
    return _sessionmaker_for(settings.timescale_url)


@contextmanager
def postgres_session(settings: Settings | None = None) -> Iterator[Session]:
    session = postgres_sessionmaker(settings)()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def timescale_session(settings: Settings | None = None) -> Iterator[Session]:
    session = timescale_sessionmaker(settings)()
    try:
        yield session
    finally:
        session.close()


def reset_engines() -> None:
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()
    _sessions.clear()
