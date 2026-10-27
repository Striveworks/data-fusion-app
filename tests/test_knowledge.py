from datetime import datetime, timezone

from app.knowledge import correct_insight, search_insights, upsert_insight
from app.db import postgres_session


def test_correction_supersedes_previous_insight(databases):
    with postgres_session(databases) as session:
        original = upsert_insight(
            session,
            subject="Two vessels loiter near the harbor",
            summary="Initial fusion from one detection.",
            entity_labels=["vessel-a"],
            place_name="Harbor",
            time_start="2026-03-01T00:00:00Z",
            time_end="2026-03-01T06:00:00Z",
            confidence=0.4,
            evidence={"detection_ids": ["old"]},
        )
        session.commit()
        original_id = original.id

        replacement = correct_insight(
            session,
            original_id,
            summary="Corrected after a second detection left the area.",
            confidence=0.8,
            evidence={"detection_ids": ["old", "new"]},
        )
        session.commit()

        active = search_insights(session, entity="vessel-a", place="Harbor")
        assert [row.id for row in active] == [replacement.id]
        assert replacement.supersedes_id == original_id
        assert replacement.status == "active"
        session.refresh(original)
        refreshed = session.get(type(original), original_id)
        assert refreshed.status == "superseded"


def test_time_filter_excludes_non_overlapping_insights(databases):
    with postgres_session(databases) as session:
        upsert_insight(
            session,
            subject="Morning activity",
            entity_labels=["unit-1"],
            place_name="North",
            time_start=datetime(2026, 3, 1, tzinfo=timezone.utc),
            time_end=datetime(2026, 3, 1, 2, tzinfo=timezone.utc),
        )
        upsert_insight(
            session,
            subject="Evening activity",
            entity_labels=["unit-1"],
            place_name="North",
            time_start=datetime(2026, 3, 1, 18, tzinfo=timezone.utc),
            time_end=datetime(2026, 3, 1, 20, tzinfo=timezone.utc),
        )
        session.commit()
        rows = search_insights(
            session,
            entity="unit-1",
            time_start="2026-03-01T00:00:00Z",
            time_end="2026-03-01T03:00:00Z",
        )
        assert [row.subject for row in rows] == ["Morning activity"]
