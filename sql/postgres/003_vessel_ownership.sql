CREATE TABLE IF NOT EXISTS metadata.vessel_ownership (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset TEXT NOT NULL DEFAULT 'vessel_ownership',
    vessel_name TEXT,
    category TEXT,
    imo TEXT,
    flag_current TEXT,
    mmsi TEXT,
    call_sign TEXT,
    vessel_type TEXT,
    length_m DOUBLE PRECISION,
    gross_tonnage DOUBLE PRECISION,
    dwt DOUBLE PRECISION,
    sanctions TEXT,
    sanction_links JSONB NOT NULL DEFAULT '[]'::jsonb,
    sanctions_person TEXT,
    picture_filename TEXT,
    source_url TEXT,
    main_photo_url TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS vessel_ownership_source_url_idx
    ON metadata.vessel_ownership (source_url);
CREATE INDEX IF NOT EXISTS vessel_ownership_imo_idx ON metadata.vessel_ownership (imo);
CREATE INDEX IF NOT EXISTS vessel_ownership_mmsi_idx ON metadata.vessel_ownership (mmsi);
CREATE INDEX IF NOT EXISTS vessel_ownership_name_idx ON metadata.vessel_ownership (vessel_name);
