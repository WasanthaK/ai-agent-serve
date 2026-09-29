BEGIN;

CREATE TABLE IF NOT EXISTS agent_requests (
    id UUID PRIMARY KEY,
    source TEXT NOT NULL,
    customer_name TEXT,
    message TEXT NOT NULL,
    intent TEXT NOT NULL,
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    urgency TEXT NOT NULL,
    next_action TEXT NOT NULL,
    needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'received',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_requests_created_at
    ON agent_requests(created_at);

CREATE INDEX IF NOT EXISTS idx_agent_requests_status
    ON agent_requests(status);

COMMIT;
