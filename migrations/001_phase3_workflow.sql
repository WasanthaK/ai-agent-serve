BEGIN;

ALTER TABLE agent_requests
    ADD COLUMN IF NOT EXISTS missing_information JSONB
        NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS follow_up_questions JSONB
        NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS actioned_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS agent_events (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL
        REFERENCES agent_requests(id)
        ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'agent',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_events_request_id
    ON agent_events(request_id);

CREATE INDEX IF NOT EXISTS idx_agent_events_created_at
    ON agent_events(created_at);

COMMIT;