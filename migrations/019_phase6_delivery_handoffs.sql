CREATE TABLE IF NOT EXISTS service_delivery_handoffs (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    award_id UUID NOT NULL UNIQUE
        REFERENCES quote_awards(id) ON DELETE RESTRICT,
    normalized_quote_id UUID NOT NULL
        REFERENCES normalized_provider_quotes(id) ON DELETE RESTRICT,
    provider_id UUID NOT NULL
        REFERENCES providers(id) ON DELETE RESTRICT,
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    currency CHAR(3) NOT NULL,
    scope_summary TEXT NOT NULL,
    exclusions JSONB NOT NULL DEFAULT '[]'::jsonb,
    terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    available_from DATE,
    estimated_duration_days INTEGER,
    activated_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT delivery_handoff_actor_nonempty
        CHECK (length(trim(activated_by)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_service_delivery_handoffs_provider
    ON service_delivery_handoffs(provider_id);
