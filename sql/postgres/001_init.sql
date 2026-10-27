CREATE SCHEMA IF NOT EXISTS metadata;

CREATE TABLE metadata.assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    modality TEXT NOT NULL CHECK (modality IN ('eo', 'sar', 'ir', 'lidar', 'fmv')),
    captured_at TIMESTAMPTZ,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    footprint JSONB,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    bucket TEXT,
    object_key TEXT,
    source_kind TEXT NOT NULL,
    external_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE metadata.triage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    watchpoint_id TEXT NOT NULL,
    chariot_event_id TEXT,
    review_status TEXT,
    captured_at TIMESTAMPTZ,
    chariot_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE metadata.detections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES metadata.assets (id),
    triage_event_id UUID REFERENCES metadata.triage_events (id),
    label TEXT NOT NULL,
    score DOUBLE PRECISION,
    geometry JSONB,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    chariot_inference_id TEXT,
    model_id TEXT,
    track_id TEXT,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX detections_label_idx ON metadata.detections (label);
CREATE INDEX detections_observed_idx ON metadata.detections (observed_at);
CREATE INDEX detections_track_idx ON metadata.detections (track_id);

CREATE TABLE metadata.jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    error TEXT,
    result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX jobs_pending_idx ON metadata.jobs (status, created_at);

CREATE TABLE metadata.knowledge_graph (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary TEXT,
    entity_labels TEXT[] NOT NULL DEFAULT '{}',
    place_name TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    time_start TIMESTAMPTZ,
    time_end TIMESTAMPTZ,
    confidence DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'corrected', 'superseded')),
    supersedes_id UUID REFERENCES metadata.knowledge_graph (id),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX knowledge_active_insight_idx
    ON metadata.knowledge_graph (predicate, status, updated_at DESC);
CREATE INDEX knowledge_place_idx ON metadata.knowledge_graph (place_name);
CREATE INDEX knowledge_entity_idx ON metadata.knowledge_graph USING GIN (entity_labels);
