CREATE TABLE IF NOT EXISTS metadata.ais_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mmsi TEXT NOT NULL,
    vessel_name TEXT,
    call_sign TEXT,
    imo TEXT,
    vessel_type INTEGER,
    vessel_type_cargo TEXT,
    length DOUBLE PRECISION,
    width DOUBLE PRECISION,
    draft DOUBLE PRECISION,
    observed_at TIMESTAMPTZ NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    speed_over_ground_knots DOUBLE PRECISION,
    course_over_ground_degrees DOUBLE PRECISION,
    heading_degrees DOUBLE PRECISION,
    navigational_status_code INTEGER,
    navigational_status TEXT,
    destination TEXT,
    eta TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ais_mmsi_time_idx ON metadata.ais_reports (mmsi, observed_at DESC);
CREATE INDEX IF NOT EXISTS ais_name_idx ON metadata.ais_reports (vessel_name);
CREATE INDEX IF NOT EXISTS ais_observed_idx ON metadata.ais_reports (observed_at);
