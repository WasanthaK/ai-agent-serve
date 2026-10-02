CREATE TABLE IF NOT EXISTS provider_selection_decisions (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    service_slug TEXT NOT NULL,
    area_key TEXT NOT NULL,
    eligible_provider_ids JSONB NOT NULL,
    selected_by TEXT NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT provider_selection_actor_nonempty
        CHECK (length(trim(selected_by)) > 0)
);

CREATE TABLE IF NOT EXISTS provider_selection_items (
    selection_id UUID NOT NULL
        REFERENCES provider_selection_decisions(id) ON DELETE CASCADE,
    provider_id UUID NOT NULL
        REFERENCES providers(id) ON DELETE RESTRICT,
    PRIMARY KEY (selection_id, provider_id)
);

CREATE INDEX IF NOT EXISTS idx_provider_selection_items_provider
    ON provider_selection_items(provider_id);
