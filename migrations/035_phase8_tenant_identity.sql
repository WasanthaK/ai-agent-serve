CREATE TABLE IF NOT EXISTS platform_tenants (
    id UUID PRIMARY KEY,
    tenant_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT platform_tenant_key_format
        CHECK (tenant_key ~ '^[a-z0-9][a-z0-9-]{0,62}$'),
    CONSTRAINT platform_tenant_display_name_nonempty
        CHECK (length(trim(display_name)) > 0),
    CONSTRAINT platform_tenant_status_valid
        CHECK (status IN ('pending', 'active', 'suspended', 'closed'))
);

CREATE INDEX IF NOT EXISTS idx_platform_tenants_status
    ON platform_tenants(status, created_at);

CREATE TABLE IF NOT EXISTS platform_tenant_events (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL
        REFERENCES platform_tenants(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT platform_tenant_event_type_nonempty
        CHECK (length(trim(event_type)) > 0),
    CONSTRAINT platform_tenant_event_actor_nonempty
        CHECK (length(trim(actor)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_platform_tenant_events_tenant
    ON platform_tenant_events(tenant_id, created_at, id);
