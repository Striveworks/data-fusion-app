CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE signal_samples (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    time TIMESTAMPTZ NOT NULL,
    modality TEXT NOT NULL CHECK (modality IN ('radar', 'elint', 'acoustic')),
    source_id TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'default',
    value DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    object_key TEXT
);

SELECT create_hypertable('signal_samples', 'time');

CREATE INDEX signal_samples_source_idx ON signal_samples (source_id, time DESC);
CREATE INDEX signal_samples_modality_idx ON signal_samples (modality, time DESC);
