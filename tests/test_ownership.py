from app.db import postgres_session, timescale_session
from app.models import VesselOwnership
from app.ownership import records_from_body
from app.processors import JobContext, dispatch
from app.queries import search_vessel_ownership
from app.storage import MemoryStore
from sqlalchemy import func, select

from tests.test_processors import FakeChariot, _settings


def test_placeholder_identifiers_are_empty():
    records = records_from_body(
        {
            "vessel_name": "ST. VITAMIN",
            "imo": "",
            "mmsi": "N/A",
            "call_sign": "N/A",
            "sanctions_person": "N/A",
            "source_url": "https://example.test/vessels/246",
            "sanction_links": ["https://ofac.treasury.gov/recent-actions/20190930"],
        }
    )
    assert records[0]["imo"] is None
    assert records[0]["mmsi"] is None
    assert records[0]["call_sign"] is None
    assert records[0]["sanction_links"] == ["https://ofac.treasury.gov/recent-actions/20190930"]


def test_ownership_upload_is_searchable(databases):
    payload = {
        "dataset": "vessel_ownership",
        "records": records_from_body(
            [
                {
                    "vessel_name": "ADLER",
                    "imo": "9179854",
                    "mmsi": "273414440",
                    "call_sign": "UGPS",
                    "flag_current": "russian federation",
                    "vessel_type": "Ro-Ro Cargo Ship",
                    "sanctions": "USA",
                    "source_url": "https://example.test/vessels/1",
                }
            ]
        ),
    }
    with postgres_session(databases) as session, timescale_session(databases) as timescale:
        result = dispatch(
            "ingest_ownership",
            JobContext(
                session=session,
                timescale=timescale,
                store=MemoryStore(),
                chariot=FakeChariot(),
                settings=_settings(),
                payload=payload,
            ),
        )
        found = search_vessel_ownership(session, "ADLER")
        stored = session.scalar(select(func.count()).select_from(VesselOwnership))
    assert result["evidence"]["record_count"] == 1
    assert stored == 1
    assert found["status"] == "ok"
    assert found["results"][0]["imo"] == "9179854"
    assert found["results"][0]["mmsi"] == "273414440"
