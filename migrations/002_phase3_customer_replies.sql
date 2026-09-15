BEGIN;

CREATE TABLE IF NOT EXISTS agent_messages (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL
        REFERENCES agent_requests(id)
        ON DELETE CASCADE,
    role TEXT NOT NULL
        CHECK (role IN ('customer', 'agent', 'human', 'system')),
    channel TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_messages_request_id
    ON agent_messages(request_id);

CREATE INDEX IF NOT EXISTS idx_agent_messages_created_at
    ON agent_messages(created_at);

COMMIT;