CREATE TABLE IF NOT EXISTS provider_service_capabilities (
    provider_id UUID NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    service_slug TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider_id, service_slug),
    CONSTRAINT provider_service_slug_not_blank
        CHECK (BTRIM(service_slug) <> ''),
    CONSTRAINT provider_service_slug_length
        CHECK (CHAR_LENGTH(service_slug) <= 100)
);

CREATE INDEX IF NOT EXISTS idx_provider_service_capabilities_service_slug
    ON provider_service_capabilities (service_slug);
