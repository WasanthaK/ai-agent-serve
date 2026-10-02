CREATE TABLE IF NOT EXISTS provider_response_opportunities (
    id UUID PRIMARY KEY,
    provider_id UUID NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    opportunity_id UUID NOT NULL,
    offered_at TIMESTAMPTZ NOT NULL,
    response_deadline_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT provider_response_deadline_after_offer
        CHECK (response_deadline_at > offered_at),
    CONSTRAINT provider_response_opportunity_unique
        UNIQUE (provider_id, opportunity_id)
);

CREATE INDEX IF NOT EXISTS idx_provider_response_opportunities_history
    ON provider_response_opportunities (provider_id, offered_at DESC);

CREATE TABLE IF NOT EXISTS provider_response_events (
    id UUID PRIMARY KEY,
    provider_id UUID NOT NULL,
    opportunity_id UUID NOT NULL,
    response_kind TEXT NOT NULL,
    responded_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT provider_response_kind_valid
        CHECK (response_kind IN ('quote', 'decline')),
    CONSTRAINT provider_response_event_unique
        UNIQUE (provider_id, opportunity_id),
    CONSTRAINT provider_response_event_opportunity_fk
        FOREIGN KEY (provider_id, opportunity_id)
        REFERENCES provider_response_opportunities(provider_id, opportunity_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_provider_response_events_history
    ON provider_response_events (provider_id, responded_at DESC);
