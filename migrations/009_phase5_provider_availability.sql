CREATE TABLE IF NOT EXISTS provider_availability (
    provider_id UUID PRIMARY KEY REFERENCES providers(id) ON DELETE CASCADE,
    availability_status TEXT NOT NULL DEFAULT 'unknown',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT provider_availability_status_valid
        CHECK (availability_status IN ('unknown', 'available', 'unavailable'))
);

CREATE INDEX IF NOT EXISTS idx_provider_availability_status
    ON provider_availability (availability_status);
