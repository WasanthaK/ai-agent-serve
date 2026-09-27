BEGIN;

ALTER TABLE agent_requests
    ADD COLUMN IF NOT EXISTS correlation_id UUID;

ALTER TABLE agent_messages
    ADD COLUMN IF NOT EXISTS correlation_id UUID;

ALTER TABLE agent_events
    ADD COLUMN IF NOT EXISTS correlation_id UUID;

CREATE INDEX IF NOT EXISTS idx_agent_requests_correlation_id
    ON agent_requests(correlation_id);

CREATE INDEX IF NOT EXISTS idx_agent_messages_correlation_id
    ON agent_messages(correlation_id);

CREATE INDEX IF NOT EXISTS idx_agent_events_correlation_id
    ON agent_events(correlation_id);

COMMIT;
