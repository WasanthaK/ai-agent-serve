BEGIN;

CREATE TABLE IF NOT EXISTS inbound_messages (
    id UUID PRIMARY KEY,
    schema_version TEXT NOT NULL,
    channel TEXT NOT NULL,
    text TEXT NOT NULL,
    sender JSONB,
    external_message_id TEXT,
    external_conversation_id TEXT,
    occurred_at TIMESTAMPTZ,
    linked_request_id UUID REFERENCES agent_requests(id) ON DELETE SET NULL,
    attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
    payload_hash TEXT NOT NULL,
    correlation_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_inbound_messages_channel_external_message
    ON inbound_messages(channel, external_message_id)
    WHERE external_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_inbound_messages_linked_request_id
    ON inbound_messages(linked_request_id);

CREATE INDEX IF NOT EXISTS idx_inbound_messages_external_conversation_id
    ON inbound_messages(channel, external_conversation_id)
    WHERE external_conversation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_inbound_messages_created_at
    ON inbound_messages(created_at);

COMMIT;
