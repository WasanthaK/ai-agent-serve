CREATE TABLE IF NOT EXISTS service_delivery_interventions (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    exception_id UUID NOT NULL UNIQUE
        REFERENCES service_delivery_exceptions(id) ON DELETE CASCADE,
    delivery_status_id UUID NOT NULL
        REFERENCES service_delivery_status(id) ON DELETE CASCADE,
    provider_id UUID NOT NULL
        REFERENCES providers(id) ON DELETE RESTRICT,
    priority TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_by TEXT,
    acknowledgement_reason TEXT,
    acknowledged_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT delivery_intervention_priority_valid
        CHECK (priority IN ('normal', 'high', 'urgent')),
    CONSTRAINT delivery_intervention_reason_nonempty
        CHECK (length(trim(reason)) > 0),
    CONSTRAINT delivery_intervention_creator_nonempty
        CHECK (length(trim(created_by)) > 0),
    CONSTRAINT delivery_intervention_status_valid
        CHECK (status IN ('open', 'acknowledged')),
    CONSTRAINT delivery_intervention_ack_consistency
        CHECK (
            (
                status = 'open'
                AND acknowledged_by IS NULL
                AND acknowledgement_reason IS NULL
                AND acknowledged_at IS NULL
            )
            OR
            (
                status = 'acknowledged'
                AND acknowledged_by IS NOT NULL
                AND length(trim(acknowledged_by)) > 0
                AND acknowledgement_reason IS NOT NULL
                AND length(trim(acknowledgement_reason)) > 0
                AND acknowledged_at IS NOT NULL
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_service_delivery_interventions_request
    ON service_delivery_interventions(request_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_service_delivery_interventions_priority
    ON service_delivery_interventions(priority, status, created_at);
