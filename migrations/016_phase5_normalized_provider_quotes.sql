CREATE TABLE IF NOT EXISTS normalized_provider_quotes (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    handoff_id UUID NOT NULL UNIQUE
        REFERENCES rfq_provider_handoffs(id) ON DELETE CASCADE,
    provider_id UUID NOT NULL
        REFERENCES providers(id) ON DELETE RESTRICT,
    response_event_id UUID NOT NULL UNIQUE
        REFERENCES provider_response_events(id) ON DELETE RESTRICT,
    amount_minor BIGINT NOT NULL,
    currency CHAR(3) NOT NULL,
    scope_summary TEXT NOT NULL,
    exclusions JSONB NOT NULL DEFAULT '[]'::jsonb,
    terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    available_from DATE,
    estimated_duration_days INTEGER,
    validity_expires_at TIMESTAMPTZ,
    normalized_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT normalized_quote_amount_nonnegative
        CHECK (amount_minor >= 0),
    CONSTRAINT normalized_quote_currency_uppercase
        CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT normalized_quote_scope_nonempty
        CHECK (length(trim(scope_summary)) > 0),
    CONSTRAINT normalized_quote_duration_positive
        CHECK (
            estimated_duration_days IS NULL
            OR estimated_duration_days > 0
        ),
    CONSTRAINT normalized_quote_actor_nonempty
        CHECK (length(trim(normalized_by)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_normalized_provider_quotes_provider
    ON normalized_provider_quotes(provider_id);
