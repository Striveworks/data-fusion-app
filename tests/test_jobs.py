from app.db import postgres_session
from app.jobs import claim_next, enqueue, mark_succeeded


def test_claim_skips_locked_pending_job(databases):
    with postgres_session(databases) as session:
        first = enqueue(session, "ingest_timeseries", {"source_id": "a"})
        second = enqueue(session, "ingest_timeseries", {"source_id": "b"})
        session.commit()
        claimed = claim_next(session)
        assert claimed.id == first.id
        assert claimed.status == "running"
        other = session.get(type(second), second.id)
        assert other.status == "pending"


def test_successful_ingest_enqueues_fusion(databases):
    with postgres_session(databases) as session:
        job = enqueue(session, "ingest_timeseries", {"source_id": "a"})
        session.commit()
        claimed = claim_next(session)
        mark_succeeded(session, claimed, {"evidence": {"signal_source_ids": ["a"]}})
        from sqlalchemy import select

        from app.models import Job

        fusion_jobs = list(session.scalars(select(Job).where(Job.kind == "run_fusion")))
        assert len(fusion_jobs) == 1
        assert fusion_jobs[0].payload["source_job_id"] == str(job.id)
        assert fusion_jobs[0].status == "pending"
