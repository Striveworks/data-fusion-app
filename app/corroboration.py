"""Adapters for corroboration sources that are not wired to a live system yet."""

from typing import Protocol


class CorroborationAdapter(Protocol):
    name: str

    def search(self, query: str) -> dict:
        """Return matching records, or an explicit unconfigured result."""


class UnconfiguredAdapter:
    def __init__(self, name: str) -> None:
        self.name = name

    def search(self, query: str) -> dict:
        return {"source": self.name, "status": "unconfigured", "query": query, "results": []}


ADAPTERS = {
    "intel_reports": None,
    "ownership": None,
    "osint": None,
}


def search_ownership(query: str) -> dict:
    from sqlalchemy.exc import SQLAlchemyError

    from app.db import postgres_session
    from app.queries import search_vessel_ownership

    try:
        with postgres_session() as session:
            return search_vessel_ownership(session, query)
    except SQLAlchemyError:
        return {"source": "ownership", "status": "unconfigured", "query": query, "results": []}


def search_osint(query: str) -> dict:
    from sqlalchemy.exc import SQLAlchemyError

    from app.db import postgres_session
    from app.queries import search_osint as query_osint

    try:
        with postgres_session() as session:
            return query_osint(session, query)
    except SQLAlchemyError:
        return {"source": "osint", "status": "unconfigured", "query": query, "results": []}


def search_intel_reports(query: str) -> dict:
    from sqlalchemy.exc import SQLAlchemyError

    from app.db import postgres_session
    from app.queries import search_intel_reports as query_intel

    try:
        with postgres_session() as session:
            return query_intel(session, query)
    except SQLAlchemyError:
        return {"source": "intel_reports", "status": "unconfigured", "query": query, "results": []}


def search_source(source: str, query: str) -> dict:
    if source == "ownership":
        return search_ownership(query)
    if source == "osint":
        return search_osint(query)
    if source == "intel_reports":
        return search_intel_reports(query)
    adapter = ADAPTERS.get(source)
    if adapter is None:
        return {"source": source, "status": "unknown", "query": query, "results": []}
    return adapter.search(query)


def probe_sources(query: str = "") -> list[dict]:
    return [search_source(name, query) for name in ADAPTERS]
