import uuid

from fastapi import APIRouter, HTTPException

from app.db import postgres_session
from app.jobs import enqueue, get_job, job_dict

router = APIRouter(prefix="/api/v1", tags=["jobs"])


@router.get("/jobs/{job_id}")
def read_job(job_id: uuid.UUID) -> dict:
    with postgres_session() as session:
        job = get_job(session, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job_dict(job)


@router.post("/fusion/run", status_code=202)
def run_fusion() -> dict:
    with postgres_session() as session:
        job = enqueue(session, "run_fusion", {"reason": "manual", "evidence": {}})
        session.commit()
        return {"job_id": str(job.id), "status": job.status}
