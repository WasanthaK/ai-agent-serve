CREATE TABLE IF NOT EXISTS service_delivery_status (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    delivery_handoff_id UUID NOT NULL UNIQUE
        REFERENCES service_delivery_handoffs(id) ON DELETE CASCADE,
    appointment_id UUID NOT NULL UNIQUE
        REFERENCES service_delivery_appointments(id) ON DELETE RESTRICT,
    provider_id UUID NOT NULL
        REFERENCES providers(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'scheduled',
    scheduled_by TEXT NOT NULL,
    scheduled_reason TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_by TEXT,
    start_reason TEXT,
    started_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT delivery_status_valid
        CHECK (status IN ('scheduled', 'in_progress')),
    CONSTRAINT delivery_status_scheduler_nonempty
        CHECK (length(trim(scheduled_by)) > 0),
    CONSTRAINT delivery_status_schedule_reason_nonempty
        CHECK (length(trim(scheduled_reason)) > 0),
    CONSTRAINT delivery_status_start_consistency
        CHECK (
            (
                status = 'scheduled'
                AND started_by IS NULL
                AND start_reason IS NULL
                AND started_at IS NULL
            )
            OR
            (
                status = 'in_progress'
                AND started_by IS NOT NULL
                AND length(trim(started_by)) > 0
                AND start_reason IS NOT NULL
                AND length(trim(start_reason)) > 0
                AND started_at IS NOT NULL
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_service_delivery_status_provider
    ON service_delivery_status(provider_id);
