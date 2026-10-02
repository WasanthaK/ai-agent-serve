CREATE TABLE IF NOT EXISTS provider_quotations (
    id UUID PRIMARY KEY,
    handoff_id UUID NOT NULL UNIQUE
        REFERENCES rfq_provider_handoffs(id) ON DELETE CASCADE,
    provider_id UUID NOT NULL
        REFERENCES providers(id) ON DELETE RESTRICT,
    currency CHAR(3) NOT NULL,
    total_amount_minor BIGINT NOT NULL,
    availability_text TEXT,
    scope_text TEXT NOT NULL,
    exclusions_text TEXT,
    terms_text TEXT,
    submitted_at TIMESTAMPTZ NOT NULL,
    recorded_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT provider_quotation_currency_format
        CHECK (currency = upper(currency) AND currency ~ '^[A-Z]{3}$'),
    CONSTRAINT provider_quotation_amount_nonnegative
        CHECK (total_amount_minor >= 0),
    CONSTRAINT provider_quotation_scope_nonempty
        CHECK (length(trim(scope_text)) > 0),
    CONSTRAINT provider_quotation_recorded_by_nonempty
        CHECK (length(trim(recorded_by)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_provider_quotations_provider
    ON provider_quotations(provider_id);
