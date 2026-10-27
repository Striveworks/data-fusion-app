import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Job

INGEST_KINDS = {
    "process_imagery",
    "sync_watchpoint",
    "sync_fmv",
    "ingest_timeseries",
    "ingest_ais",
    "ingest_ownership",
    "ingest_osint",
    "ingest_intel",
}


def enqueue(session: Session, kind: str, payload: dict) -> Job:
    job = Job(kind=kind, payload=payload, status="pending")
    session.add(job)
    session.flush()
    return job


def claim_next(session: Session) -> Job | None:
    row = session.execute(
        text(
            """
            UPDATE metadata.jobs
            SET status = 'running', started_at = now()
            WHERE id = (
                SELECT id
                FROM metadata.jobs
                WHERE status = 'pending'
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id
            """
        )
    ).first()
    if row is None:
        return None
    session.commit()
    return session.get(Job, row[0], populate_existing=True)


def mark_succeeded(session: Session, job: Job, result: dict | None) -> None:
    job.status = "succeeded"
    job.result = result
    job.error = None
    job.finished_at = datetime.now(timezone.utc)
    if job.kind in INGEST_KINDS:
        enqueue(
            session,
            "run_fusion",
            {
                "reason": "ingest_complete",
                "source_job_id": str(job.id),
                "evidence": (result or {}).get("evidence", {}),
            },
        )
    session.commit()


def mark_failed(session: Session, job_id: uuid.UUID, error: str) -> None:
    session.rollback()
    job = session.get(Job, job_id)
    if job is None:
        return
    job.status = "failed"
    job.error = error
    job.finished_at = datetime.now(timezone.utc)
    session.commit()


def get_job(session: Session, job_id: uuid.UUID) -> Job | None:
    return session.get(Job, job_id)


def recent_jobs(session: Session, limit: int = 12) -> list[Job]:
    query = select(Job).order_by(Job.created_at.desc()).limit(limit)
    return list(session.scalars(query))


def job_dict(job: Job) -> dict:
    return {
        "id": str(job.id),
        "kind": job.kind,
        "status": job.status,
        "payload": job.payload or {},
        "error": job.error,
        "result": job.result,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
