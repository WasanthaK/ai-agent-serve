CREATE TABLE IF NOT EXISTS provider_compliance (
    provider_id UUID PRIMARY KEY REFERENCES providers(id) ON DELETE CASCADE,
    compliance_status TEXT NOT NULL DEFAULT 'unknown',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT provider_compliance_status_valid
        CHECK (compliance_status IN ('unknown', 'compliant', 'non_compliant'))
);

CREATE INDEX IF NOT EXISTS idx_provider_compliance_status
    ON provider_compliance (compliance_status);
