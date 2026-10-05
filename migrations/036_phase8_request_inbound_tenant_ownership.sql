ALTER TABLE agent_requests
    ADD COLUMN IF NOT EXISTS tenant_id UUID
        REFERENCES platform_tenants(id) ON DELETE RESTRICT;

ALTER TABLE inbound_messages
    ADD COLUMN IF NOT EXISTS tenant_id UUID
        REFERENCES platform_tenants(id) ON DELETE RESTRICT;

ALTER TABLE webhook_idempotency
    ADD COLUMN IF NOT EXISTS tenant_id UUID
        REFERENCES platform_tenants(id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS idx_agent_requests_tenant
    ON agent_requests(tenant_id, created_at);

CREATE INDEX IF NOT EXISTS idx_inbound_messages_tenant
    ON inbound_messages(tenant_id, created_at);

DROP INDEX IF EXISTS uq_inbound_messages_channel_external_message;

CREATE UNIQUE INDEX IF NOT EXISTS uq_inbound_messages_legacy_channel_external
    ON inbound_messages(channel, external_message_id)
    WHERE external_message_id IS NOT NULL
      AND tenant_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_inbound_messages_tenant_channel_external
    ON inbound_messages(tenant_id, channel, external_message_id)
    WHERE external_message_id IS NOT NULL
      AND tenant_id IS NOT NULL;

ALTER TABLE webhook_idempotency
    DROP CONSTRAINT IF EXISTS webhook_idempotency_pkey;

CREATE UNIQUE INDEX IF NOT EXISTS uq_webhook_idempotency_legacy_source_key
    ON webhook_idempotency(source, idempotency_key_hash)
    WHERE tenant_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_webhook_idempotency_tenant_source_key
    ON webhook_idempotency(tenant_id, source, idempotency_key_hash)
    WHERE tenant_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_webhook_idempotency_tenant
    ON webhook_idempotency(tenant_id, created_at);
