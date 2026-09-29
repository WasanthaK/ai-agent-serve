CREATE TABLE IF NOT EXISTS provider_coverage_areas (
    provider_id UUID NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    area_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider_id, area_key),
    CONSTRAINT provider_coverage_area_key_not_blank
        CHECK (BTRIM(area_key) <> ''),
    CONSTRAINT provider_coverage_area_key_length
        CHECK (CHAR_LENGTH(area_key) <= 120)
);

CREATE INDEX IF NOT EXISTS idx_provider_coverage_areas_area_key
    ON provider_coverage_areas (area_key);
