import json
import uuid

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.elint import parse_elint_document
from app.intel import parse_intel_document, records_from_body as intel_records_from_body
from app.osint import parse_osint_document, records_from_body as osint_records_from_body
from app.ownership import parse_ownership_document, records_from_body
from app.config import get_settings
from app.db import postgres_session
from app.jobs import enqueue
from app.storage import MinioStore
from app.timeutil import parse_time

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

MODALITIES = {"eo", "sar", "ir", "lidar", "fmv"}
SIGNAL_MODALITIES = {"radar", "elint", "acoustic"}


class WatchpointRequest(BaseModel):
    watchpoint_id: str
    project_id: str
    time_start: str | None = None
    time_end: str | None = None


class FmvRequest(BaseModel):
    model_id: str
    feed_id: str
    time_start: str | None = None
    time_end: str | None = None


class Sample(BaseModel):
    time: str
    value: float | None = None
    channel: str = "default"
    latitude: float | None = None
    longitude: float | None = None
    details: dict = Field(default_factory=dict)


class TimeseriesRequest(BaseModel):
    modality: str
    source_id: str = ""
    samples: list[Sample] = Field(default_factory=list)
    captured_at: str | None = None
    latitude: float | None = None
    longitude: float | None = None


def _accept(kind: str, payload: dict, extra: dict | None = None) -> JSONResponse:
    with postgres_session() as session:
        job = enqueue(session, kind, payload)
        session.commit()
        job_id = job.id
    body = {"job_id": str(job_id), "status": "pending"}
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=202)


def _store() -> MinioStore:
    settings = get_settings()
    return MinioStore(
        settings.minio_endpoint,
        settings.minio_access_key,
        settings.minio_secret_key,
        settings.minio_bucket,
        settings.minio_secure,
    )


@router.post("/imagery")
async def ingest_imagery(
    file: UploadFile = File(...),
    modality: str = Form(...),
    metadata: str = Form("{}"),
    captured_at: str | None = Form(None),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    external_id: str | None = Form(None),
    footprint: str | None = Form(None),
) -> JSONResponse:
    if modality not in MODALITIES:
        raise HTTPException(status_code=422, detail="modality must be eo, sar, ir, lidar, or fmv")
    try:
        details = json.loads(metadata)
        footprint_data = json.loads(footprint) if footprint else None
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="metadata and footprint must be JSON") from exc
    if not isinstance(details, dict):
        raise HTTPException(status_code=422, detail="metadata must be a JSON object")
    if captured_at:
        parse_time(captured_at)

    data = await file.read()
    inbox_key = f"inbox/{uuid.uuid4()}"
    _store().put(inbox_key, data, file.content_type or "application/octet-stream")
    return _accept(
        "process_imagery",
        {
            "inbox_key": inbox_key,
            "filename": file.filename,
            "content_type": file.content_type,
            "modality": modality,
            "metadata": details,
            "captured_at": captured_at,
            "latitude": latitude,
            "longitude": longitude,
            "external_id": external_id,
            "footprint": footprint_data,
        },
    )


@router.post("/watchpoint")
def ingest_watchpoint(body: WatchpointRequest) -> JSONResponse:
    if body.time_start:
        parse_time(body.time_start)
    if body.time_end:
        parse_time(body.time_end)
    return _accept("sync_watchpoint", body.model_dump())


@router.post("/fmv")
def ingest_fmv(body: FmvRequest) -> JSONResponse:
    if body.time_start:
        parse_time(body.time_start)
    if body.time_end:
        parse_time(body.time_end)
    return _accept("sync_fmv", body.model_dump())


@router.post("/ais")
async def ingest_ais(request: Request) -> JSONResponse:
    content_type = request.headers.get("content-type", "")
    filename = "ais.json"
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        pasted = form.get("reports")
        if upload is not None and hasattr(upload, "read") and upload.filename:
            raw = await upload.read()
            filename = upload.filename
            content_type = upload.content_type or "application/json"
        elif isinstance(pasted, str) and pasted.strip():
            raw = pasted.encode()
            content_type = "application/json"
        else:
            raise HTTPException(status_code=422, detail="Choose an AIS JSON file or paste reports")
    else:
        raw = await request.body()
    if not raw.strip():
        raise HTTPException(status_code=422, detail="AIS body is empty")
    inbox_key = f"inbox/{uuid.uuid4()}"
    _store().put(inbox_key, raw, content_type or "application/json")
    return _accept(
        "ingest_ais",
        {
            "inbox_key": inbox_key,
            "filename": filename,
            "content_type": content_type or "application/json",
            "size_bytes": len(raw),
        },
    )


@router.post("/ownership")
async def ingest_ownership(request: Request) -> JSONResponse:
    content_type = request.headers.get("content-type", "")
    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            upload = form.get("file")
            pasted = form.get("records")
            dataset = form.get("dataset")
            if upload is not None and hasattr(upload, "read") and upload.filename:
                records = parse_ownership_document(await upload.read())
            elif isinstance(pasted, str) and pasted.strip():
                records = parse_ownership_document(pasted)
            else:
                raise ValueError("Choose an ownership JSON file or paste records")
            dataset_name = dataset.strip() if isinstance(dataset, str) and dataset.strip() else "vessel_ownership"
        else:
            body = await request.json()
            records = records_from_body(body)
            dataset_name = "vessel_ownership"
            if isinstance(body, dict) and isinstance(body.get("dataset"), str) and body["dataset"].strip():
                dataset_name = body["dataset"].strip()
    except (json.JSONDecodeError, ValueError) as exc:
        detail = "Ownership body must be JSON" if isinstance(exc, json.JSONDecodeError) else str(exc)
        raise HTTPException(status_code=422, detail=detail) from exc
    return _accept(
        "ingest_ownership",
        {"dataset": dataset_name, "records": records},
        extra={"accepted": len(records)},
    )


@router.post("/osint")
async def ingest_osint(request: Request) -> JSONResponse:
    content_type = request.headers.get("content-type", "")
    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            upload = form.get("file")
            pasted = form.get("report")
            if upload is not None and hasattr(upload, "read") and upload.filename:
                reports = parse_osint_document(await upload.read())
            elif isinstance(pasted, str) and pasted.strip():
                reports = parse_osint_document(pasted)
            else:
                raise ValueError("Choose an OSINT file or paste a report")
        else:
            body = await request.json()
            if isinstance(body, str):
                reports = parse_osint_document(body)
            else:
                reports = osint_records_from_body(body)
    except (json.JSONDecodeError, ValueError) as exc:
        detail = "OSINT body must be a report" if isinstance(exc, json.JSONDecodeError) else str(exc)
        raise HTTPException(status_code=422, detail=detail) from exc
    return _accept("ingest_osint", {"reports": reports}, extra={"accepted": len(reports)})


@router.post("/intel")
async def ingest_intel(request: Request) -> JSONResponse:
    content_type = request.headers.get("content-type", "")
    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            upload = form.get("file")
            pasted = form.get("report")
            if upload is not None and hasattr(upload, "read") and upload.filename:
                reports = parse_intel_document(await upload.read())
            elif isinstance(pasted, str) and pasted.strip():
                reports = parse_intel_document(pasted)
            else:
                raise ValueError("Choose an intel report file or paste a report")
        else:
            body = await request.json()
            if isinstance(body, str):
                reports = parse_intel_document(body)
            else:
                reports = intel_records_from_body(body)
    except (json.JSONDecodeError, ValueError) as exc:
        detail = "Intel body must be a report" if isinstance(exc, json.JSONDecodeError) else str(exc)
        raise HTTPException(status_code=422, detail=detail) from exc
    return _accept("ingest_intel", {"reports": reports}, extra={"accepted": len(reports)})


@router.post("/timeseries")
async def ingest_timeseries(request: Request) -> JSONResponse:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        encoded = json.dumps(body).encode()
        intercepts = parse_elint_document(encoded)
        if intercepts and not (isinstance(body, dict) and body.get("samples")):
            inbox_key = f"inbox/{uuid.uuid4()}"
            _store().put(inbox_key, encoded, "application/json")
            source_id = body.get("source_id") if isinstance(body, dict) else ""
            return _accept(
                "ingest_timeseries",
                {
                    "modality": "elint",
                    "source_id": source_id or "",
                    "inbox_key": inbox_key,
                    "filename": "elint.json",
                    "content_type": "application/json",
                },
                extra={"accepted": len(intercepts)},
            )
        payload = TimeseriesRequest.model_validate(body)
        if payload.modality not in SIGNAL_MODALITIES:
            raise HTTPException(status_code=422, detail="modality must be radar, elint, or acoustic")
        if not payload.samples:
            raise HTTPException(status_code=422, detail="samples are required when no file is uploaded")
        for sample in payload.samples:
            parse_time(sample.time)
        return _accept("ingest_timeseries", payload.model_dump())

    form = await request.form()
    raw_body = form.get("body")
    upload = form.get("file")
    if not isinstance(raw_body, str):
        raise HTTPException(status_code=422, detail="multipart ingest requires a JSON body field")
    try:
        payload = TimeseriesRequest.model_validate(json.loads(raw_body))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="body must be a timeseries JSON object") from exc
    if payload.modality not in SIGNAL_MODALITIES:
        raise HTTPException(status_code=422, detail="modality must be radar, elint, or acoustic")
    data = payload.model_dump()
    if upload is not None and hasattr(upload, "read"):
        contents = await upload.read()
        inbox_key = f"inbox/{uuid.uuid4()}"
        _store().put(inbox_key, contents, upload.content_type or "application/octet-stream")
        data["inbox_key"] = inbox_key
        data["filename"] = upload.filename
        data["content_type"] = upload.content_type
    elif not payload.samples:
        raise HTTPException(status_code=422, detail="provide samples or a file")
    return _accept("ingest_timeseries", data)
