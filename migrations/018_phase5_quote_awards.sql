CREATE TABLE IF NOT EXISTS quote_awards (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    recommendation_id UUID NOT NULL UNIQUE
        REFERENCES quote_recommendations(id) ON DELETE RESTRICT,
    normalized_quote_id UUID NOT NULL UNIQUE
        REFERENCES normalized_provider_quotes(id) ON DELETE RESTRICT,
    provider_id UUID NOT NULL
        REFERENCES providers(id) ON DELETE RESTRICT,
    awarded_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT quote_award_actor_nonempty
        CHECK (length(trim(awarded_by)) > 0),
    CONSTRAINT quote_award_reason_nonempty
        CHECK (length(trim(reason)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_quote_awards_provider
    ON quote_awards(provider_id);
