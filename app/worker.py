import logging
import signal
import time

from app.chariot import ChariotGateway
from app.config import get_settings
from app.db import postgres_session, timescale_session
from app.jobs import claim_next, mark_failed, mark_succeeded
from app.models import Job
from app.processors import JobContext, dispatch
from app.storage import MinioStore

logger = logging.getLogger(__name__)
_stop = False


def _request_stop(signum, _frame) -> None:
    global _stop
    _stop = True
    logger.info("Stopping worker after the current job (signal %s)", signum)


def run_once() -> bool:
    settings = get_settings()
    with postgres_session(settings) as session:
        job = claim_next(session)
        if job is None:
            return False
        job_id = job.id
        kind = job.kind
        payload = dict(job.payload or {})

    store = MinioStore(
        settings.minio_endpoint,
        settings.minio_access_key,
        settings.minio_secret_key,
        settings.minio_bucket,
        settings.minio_secure,
    )
    chariot = ChariotGateway(settings)
    with postgres_session(settings) as session, timescale_session(settings) as timescale:
        ctx = JobContext(
            session=session,
            timescale=timescale,
            store=store,
            chariot=chariot,
            settings=settings,
            payload=payload,
        )
        try:
            result = dispatch(kind, ctx)
            current = session.get(Job, job_id)
            mark_succeeded(session, current, result)
            logger.info("Job %s (%s) succeeded", job_id, kind)
        except Exception as exc:
            logger.exception("Job %s (%s) failed", job_id, kind)
            mark_failed(session, job_id, str(exc))
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    settings = get_settings()
    logger.info("Fusion worker polling every %ss", settings.worker_poll_seconds)
    while not _stop:
        try:
            worked = run_once()
        except Exception:
            logger.exception("Worker loop error")
            worked = False
        if not worked and not _stop:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
