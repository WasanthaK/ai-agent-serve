CREATE TABLE IF NOT EXISTS quote_recommendations (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    normalized_quote_id UUID NOT NULL UNIQUE
        REFERENCES normalized_provider_quotes(id) ON DELETE RESTRICT,
    recommended_by TEXT NOT NULL,
    rationale TEXT NOT NULL,
    comparison_snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT quote_recommendation_actor_nonempty
        CHECK (length(trim(recommended_by)) > 0),
    CONSTRAINT quote_recommendation_rationale_nonempty
        CHECK (length(trim(rationale)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_quote_recommendations_quote
    ON quote_recommendations(normalized_quote_id);
