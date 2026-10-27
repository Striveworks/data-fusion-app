import json
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.intel import parse_intel_document
from app.osint import parse_osint_document
from app.ownership import parse_ownership_document
from app.api.ingest import FmvRequest, Sample, TimeseriesRequest, WatchpointRequest
from app.api.ingest import _accept as accept_ingest
from app.api.ingest import _store as ingest_store
from app.api.ingest import ingest_fmv, ingest_imagery, ingest_watchpoint
from app.corroboration import probe_sources
from app.db import postgres_session
from app.jobs import enqueue, get_job, job_dict, recent_jobs
from app.knowledge import get_statement, search_insights, statement_dict
from app.timeutil import parse_time

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/")
def insights_page(
    request: Request,
    entity: str | None = None,
    place: str | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
):
    with postgres_session() as session:
        insights = [
            statement_dict(row)
            for row in search_insights(
                session,
                entity=entity,
                place=place,
                time_start=time_start,
                time_end=time_end,
            )
        ]
        jobs = [job_dict(job) for job in recent_jobs(session)]
    return templates.TemplateResponse(
        "insights.html",
        {
            "request": request,
            "insights": insights,
            "jobs": jobs,
            "filters": {
                "entity": entity or "",
                "place": place or "",
                "time_start": time_start or "",
                "time_end": time_end or "",
            },
            "sources": probe_sources(entity or ""),
        },
    )


@router.get("/insights/{insight_id}")
def insight_detail(request: Request, insight_id: str):
    import uuid

    try:
        parsed = uuid.UUID(insight_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Insight not found") from exc
    with postgres_session() as session:
        row = get_statement(session, parsed)
        if row is None:
            raise HTTPException(status_code=404, detail="Insight not found")
        payload = statement_dict(row)
    return templates.TemplateResponse(
        "insight_detail.html",
        {
            "request": request,
            "insight": payload,
            "sources": probe_sources(payload["subject"]),
        },
    )


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _float_field(value: str | None, label: str) -> float | None:
    text = _blank(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{label} must be a number") from exc


def _ingest_page(request: Request, *, kind: str = "imagery", error: str | None = None, job: dict | None = None):
    return templates.TemplateResponse(
        "ingest.html",
        {"request": request, "kind": kind, "error": error, "job": job},
        status_code=422 if error else 200,
    )


def _queued(response) -> RedirectResponse:
    payload = json.loads(response.body)
    return RedirectResponse(url=f"/ingest?job_id={payload['job_id']}", status_code=303)


@router.get("/ingest")
def ingest_page(request: Request, job_id: str | None = None, kind: str | None = None):
    job = None
    selected = (
        kind
        if kind in {"imagery", "watchpoint", "fmv", "timeseries", "ais", "ownership", "osint", "intel"}
        else "imagery"
    )
    if job_id:
        try:
            parsed = uuid.UUID(job_id)
        except ValueError:
            parsed = None
        if parsed is not None:
            with postgres_session() as session:
                row = get_job(session, parsed)
                if row is not None:
                    job = job_dict(row)
                    selected = {
                        "process_imagery": "imagery",
                        "sync_watchpoint": "watchpoint",
                        "sync_fmv": "fmv",
                        "ingest_timeseries": "timeseries",
                        "ingest_ais": "ais",
                        "ingest_ownership": "ownership",
                        "ingest_osint": "osint",
                        "ingest_intel": "intel",
                    }.get(row.kind, selected)
    return _ingest_page(request, kind=selected, job=job)


@router.post("/ingest/imagery")
async def submit_imagery(
    request: Request,
    file: UploadFile | None = File(None),
    modality: str = Form(...),
    metadata: str = Form("{}"),
    captured_at: str | None = Form(None),
    latitude: str | None = Form(None),
    longitude: str | None = Form(None),
    external_id: str | None = Form(None),
    footprint: str | None = Form(None),
):
    try:
        if file is None or not file.filename:
            raise HTTPException(status_code=422, detail="Choose an image file")
        response = await ingest_imagery(
            file=file,
            modality=modality,
            metadata=metadata or "{}",
            captured_at=_blank(captured_at),
            latitude=_float_field(latitude, "Latitude"),
            longitude=_float_field(longitude, "Longitude"),
            external_id=_blank(external_id),
            footprint=_blank(footprint),
        )
    except HTTPException as exc:
        return _ingest_page(request, kind="imagery", error=str(exc.detail))
    except ValueError as exc:
        return _ingest_page(request, kind="imagery", error=str(exc))
    return _queued(response)


@router.post("/ingest/watchpoint")
def submit_watchpoint(
    request: Request,
    watchpoint_id: str = Form(""),
    project_id: str = Form(""),
    time_start: str | None = Form(None),
    time_end: str | None = Form(None),
):
    try:
        if not watchpoint_id.strip() or not project_id.strip():
            raise HTTPException(status_code=422, detail="Watch point id and project id are required")
        response = ingest_watchpoint(
            WatchpointRequest(
                watchpoint_id=watchpoint_id.strip(),
                project_id=project_id.strip(),
                time_start=_blank(time_start),
                time_end=_blank(time_end),
            )
        )
    except (HTTPException, ValidationError, ValueError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return _ingest_page(request, kind="watchpoint", error=str(detail))
    return _queued(response)


@router.post("/ingest/fmv")
def submit_fmv(
    request: Request,
    model_id: str = Form(""),
    feed_id: str = Form(""),
    time_start: str | None = Form(None),
    time_end: str | None = Form(None),
):
    try:
        if not model_id.strip() or not feed_id.strip():
            raise HTTPException(status_code=422, detail="Model id and feed id are required")
        response = ingest_fmv(
            FmvRequest(
                model_id=model_id.strip(),
                feed_id=feed_id.strip(),
                time_start=_blank(time_start),
                time_end=_blank(time_end),
            )
        )
    except (HTTPException, ValidationError, ValueError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return _ingest_page(request, kind="fmv", error=str(detail))
    return _queued(response)


@router.post("/ingest/timeseries")
async def submit_timeseries(
    request: Request,
    modality: str = Form(...),
    source_id: str = Form(""),
    samples: str = Form(""),
    captured_at: str | None = Form(None),
    latitude: str | None = Form(None),
    longitude: str | None = Form(None),
    file: UploadFile | None = File(None),
):
    try:
        raw_samples = json.loads(samples) if samples.strip() else []
        if not isinstance(raw_samples, list):
            raise HTTPException(status_code=422, detail="Samples must be a JSON array")
        parsed_samples = [Sample.model_validate(item) for item in raw_samples]
        payload = TimeseriesRequest(
            modality=modality,
            source_id=source_id.strip(),
            samples=parsed_samples,
            captured_at=_blank(captured_at),
            latitude=_float_field(latitude, "Latitude"),
            longitude=_float_field(longitude, "Longitude"),
        )
        has_file = file is not None and bool(file.filename)
        json_file = has_file and str(file.filename).lower().endswith(".json")
        if not payload.source_id and not json_file:
            raise HTTPException(status_code=422, detail="Source id is required")
        if payload.modality not in {"radar", "elint", "acoustic"}:
            raise HTTPException(status_code=422, detail="modality must be radar, elint, or acoustic")
        if not payload.samples and not has_file:
            raise HTTPException(status_code=422, detail="Provide samples or a file")
        if not payload.samples and not json_file and payload.captured_at is None:
            raise HTTPException(status_code=422, detail="A file without samples needs a capture time")
        for sample in payload.samples:
            parse_time(sample.time)
        data = payload.model_dump()
        if has_file:
            contents = await file.read()
            inbox_key = f"inbox/{uuid.uuid4()}"
            ingest_store().put(inbox_key, contents, file.content_type or "application/octet-stream")
            data["inbox_key"] = inbox_key
            data["filename"] = file.filename
            data["content_type"] = file.content_type
        response = accept_ingest("ingest_timeseries", data)
    except (HTTPException, ValidationError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, HTTPException):
            detail = exc.detail
        elif isinstance(exc, json.JSONDecodeError):
            detail = "Samples must be JSON"
        else:
            detail = str(exc)
        return _ingest_page(request, kind="timeseries", error=str(detail))
    return _queued(response)


@router.post("/ingest/ais")
async def submit_ais(
    request: Request,
    reports: str = Form(""),
    file: UploadFile | None = File(None),
):
    try:
        if file is not None and file.filename:
            raw = await file.read()
            filename = file.filename
            content_type = file.content_type or "application/json"
        elif reports.strip():
            raw = reports.encode()
            filename = "ais.json"
            content_type = "application/json"
        else:
            raise ValueError("Choose an AIS JSON file or paste reports")
        inbox_key = f"inbox/{uuid.uuid4()}"
        ingest_store().put(inbox_key, raw, content_type)
        response = accept_ingest(
            "ingest_ais",
            {
                "inbox_key": inbox_key,
                "filename": filename,
                "content_type": content_type,
                "size_bytes": len(raw),
            },
        )
    except (HTTPException, ValueError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return _ingest_page(request, kind="ais", error=str(detail))
    return _queued(response)


@router.post("/ingest/ownership")
async def submit_ownership(
    request: Request,
    records: str = Form(""),
    dataset: str = Form("vessel_ownership"),
    file: UploadFile | None = File(None),
):
    try:
        if file is not None and file.filename:
            parsed = parse_ownership_document(await file.read())
        elif records.strip():
            parsed = parse_ownership_document(records)
        else:
            raise ValueError("Choose an ownership JSON file or paste records")
        response = accept_ingest(
            "ingest_ownership",
            {"dataset": dataset.strip() or "vessel_ownership", "records": parsed},
        )
    except (HTTPException, ValueError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return _ingest_page(request, kind="ownership", error=str(detail))
    return _queued(response)


@router.post("/ingest/osint")
async def submit_osint(
    request: Request,
    report: str = Form(""),
    file: UploadFile | None = File(None),
):
    try:
        if file is not None and file.filename:
            parsed = parse_osint_document(await file.read())
        elif report.strip():
            parsed = parse_osint_document(report)
        else:
            raise ValueError("Choose an OSINT file or paste a report")
        response = accept_ingest("ingest_osint", {"reports": parsed})
    except (HTTPException, ValueError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return _ingest_page(request, kind="osint", error=str(detail))
    return _queued(response)


@router.post("/ingest/intel")
async def submit_intel(
    request: Request,
    report: str = Form(""),
    file: UploadFile | None = File(None),
):
    try:
        if file is not None and file.filename:
            parsed = parse_intel_document(await file.read())
        elif report.strip():
            parsed = parse_intel_document(report)
        else:
            raise ValueError("Choose an intel report file or paste a report")
        response = accept_ingest("ingest_intel", {"reports": parsed})
    except (HTTPException, ValueError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return _ingest_page(request, kind="intel", error=str(detail))
    return _queued(response)


@router.post("/fusion/run")
def enqueue_fusion_from_dashboard():
    with postgres_session() as session:
        enqueue(session, "run_fusion", {"reason": "manual", "evidence": {}})
        session.commit()
    return RedirectResponse(url="/", status_code=303)
