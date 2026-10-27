CREATE TABLE IF NOT EXISTS metadata.intel_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_key TEXT NOT NULL,
    title TEXT,
    classification TEXT,
    subject TEXT,
    person_name TEXT,
    vessel_name TEXT,
    imo TEXT,
    mmsi TEXT,
    status TEXT,
    event_date DATE,
    summary TEXT,
    body TEXT NOT NULL,
    source TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS intel_reports_key_idx
    ON metadata.intel_reports (report_key);
CREATE INDEX IF NOT EXISTS intel_reports_imo_idx ON metadata.intel_reports (imo);
CREATE INDEX IF NOT EXISTS intel_reports_person_idx ON metadata.intel_reports (person_name);
CREATE INDEX IF NOT EXISTS intel_reports_vessel_idx ON metadata.intel_reports (vessel_name);
