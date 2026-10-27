import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = {"schema": "metadata"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    modality: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    footprint: Mapped[dict | None] = mapped_column(JSONB)
    details: Mapped[dict] = mapped_column("details", JSONB, nullable=False, default=dict)
    bucket: Mapped[str | None] = mapped_column(Text)
    object_key: Mapped[str | None] = mapped_column(Text)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TriageEvent(Base):
    __tablename__ = "triage_events"
    __table_args__ = {"schema": "metadata"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    watchpoint_id: Mapped[str] = mapped_column(Text, nullable=False)
    chariot_event_id: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chariot_ids: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Detection(Base):
    __tablename__ = "detections"
    __table_args__ = {"schema": "metadata"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    triage_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    label: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    geometry: Mapped[dict | None] = mapped_column(JSONB)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    chariot_inference_id: Mapped[str | None] = mapped_column(Text)
    model_id: Mapped[str | None] = mapped_column(Text)
    track_id: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = {"schema": "metadata"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeStatement(Base):
    __tablename__ = "knowledge_graph"
    __table_args__ = {"schema": "metadata"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    predicate: Mapped[str] = mapped_column(Text, nullable=False)
    object_data: Mapped[dict] = mapped_column("object", JSONB, nullable=False, default=dict)
    summary: Mapped[str | None] = mapped_column(Text)
    entity_labels: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    place_name: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    time_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AisReport(Base):
    __tablename__ = "ais_reports"
    __table_args__ = {"schema": "metadata"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mmsi: Mapped[str] = mapped_column(Text, nullable=False)
    vessel_name: Mapped[str | None] = mapped_column(Text)
    call_sign: Mapped[str | None] = mapped_column(Text)
    imo: Mapped[str | None] = mapped_column(Text)
    vessel_type: Mapped[int | None] = mapped_column(Integer)
    vessel_type_cargo: Mapped[str | None] = mapped_column(Text)
    length: Mapped[float | None] = mapped_column(Float)
    width: Mapped[float | None] = mapped_column(Float)
    draft: Mapped[float | None] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    speed_over_ground_knots: Mapped[float | None] = mapped_column(Float)
    course_over_ground_degrees: Mapped[float | None] = mapped_column(Float)
    heading_degrees: Mapped[float | None] = mapped_column(Float)
    navigational_status_code: Mapped[int | None] = mapped_column(Integer)
    navigational_status: Mapped[str | None] = mapped_column(Text)
    destination: Mapped[str | None] = mapped_column(Text)
    eta: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VesselOwnership(Base):
    __tablename__ = "vessel_ownership"
    __table_args__ = {"schema": "metadata"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset: Mapped[str] = mapped_column(Text, nullable=False, default="vessel_ownership")
    vessel_name: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    imo: Mapped[str | None] = mapped_column(Text)
    flag_current: Mapped[str | None] = mapped_column(Text)
    mmsi: Mapped[str | None] = mapped_column(Text)
    call_sign: Mapped[str | None] = mapped_column(Text)
    vessel_type: Mapped[str | None] = mapped_column(Text)
    length_m: Mapped[float | None] = mapped_column(Float)
    gross_tonnage: Mapped[float | None] = mapped_column(Float)
    dwt: Mapped[float | None] = mapped_column(Float)
    sanctions: Mapped[str | None] = mapped_column(Text)
    sanction_links: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    sanctions_person: Mapped[str | None] = mapped_column(Text)
    picture_filename: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    main_photo_url: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OsintReport(Base):
    __tablename__ = "osint_reports"
    __table_args__ = {"schema": "metadata"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_key: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    vessel_name: Mapped[str | None] = mapped_column(Text)
    imo: Mapped[str | None] = mapped_column(Text)
    mmsi: Mapped[str | None] = mapped_column(Text)
    flag: Mapped[str | None] = mapped_column(Text)
    vessel_type: Mapped[str | None] = mapped_column(Text)
    event: Mapped[str | None] = mapped_column(Text)
    event_date: Mapped[date | None] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)
    origin: Mapped[str | None] = mapped_column(Text)
    destination: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntelReport(Base):
    __tablename__ = "intel_reports"
    __table_args__ = {"schema": "metadata"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_key: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    person_name: Mapped[str | None] = mapped_column(Text)
    vessel_name: Mapped[str | None] = mapped_column(Text)
    imo: Mapped[str | None] = mapped_column(Text)
    mmsi: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    event_date: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SignalSample(Base):
    __tablename__ = "signal_samples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    modality: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False, default="default")
    value: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    object_key: Mapped[str | None] = mapped_column(Text)
