CREATE TABLE IF NOT EXISTS metadata.osint_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_key TEXT NOT NULL,
    title TEXT,
    vessel_name TEXT,
    imo TEXT,
    mmsi TEXT,
    flag TEXT,
    vessel_type TEXT,
    event TEXT,
    event_date DATE,
    report_date DATE,
    origin TEXT,
    destination TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    summary TEXT,
    body TEXT NOT NULL,
    source TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS osint_reports_key_idx
    ON metadata.osint_reports (report_key);
CREATE INDEX IF NOT EXISTS osint_reports_imo_idx ON metadata.osint_reports (imo);
CREATE INDEX IF NOT EXISTS osint_reports_mmsi_idx ON metadata.osint_reports (mmsi);
CREATE INDEX IF NOT EXISTS osint_reports_name_idx ON metadata.osint_reports (vessel_name);
