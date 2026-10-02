CREATE TABLE IF NOT EXISTS rfqs (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    selection_id UUID NOT NULL UNIQUE
        REFERENCES provider_selection_decisions(id) ON DELETE CASCADE,
    service_slug TEXT NOT NULL,
    area_key TEXT NOT NULL,
    scope_summary TEXT NOT NULL,
    urgency TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'prepared',
    prepared_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT rfq_status_prepared_only
        CHECK (status = 'prepared'),
    CONSTRAINT rfq_prepared_by_nonempty
        CHECK (length(trim(prepared_by)) > 0),
    CONSTRAINT rfq_scope_summary_nonempty
        CHECK (length(trim(scope_summary)) > 0)
);

CREATE TABLE IF NOT EXISTS rfq_provider_handoffs (
    id UUID PRIMARY KEY,
    rfq_id UUID NOT NULL
        REFERENCES rfqs(id) ON DELETE CASCADE,
    provider_id UUID NOT NULL
        REFERENCES providers(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'prepared',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT rfq_provider_handoff_status_prepared_only
        CHECK (status = 'prepared'),
    CONSTRAINT rfq_provider_handoff_unique
        UNIQUE (rfq_id, provider_id)
);

CREATE INDEX IF NOT EXISTS idx_rfq_provider_handoffs_provider
    ON rfq_provider_handoffs(provider_id);
