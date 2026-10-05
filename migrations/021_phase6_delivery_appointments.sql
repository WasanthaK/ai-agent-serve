CREATE TABLE IF NOT EXISTS service_delivery_appointments (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    delivery_handoff_id UUID NOT NULL UNIQUE
        REFERENCES service_delivery_handoffs(id) ON DELETE CASCADE,
    provider_id UUID NOT NULL
        REFERENCES providers(id) ON DELETE RESTRICT,
    proposed_start_at TIMESTAMPTZ NOT NULL,
    proposed_end_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    proposed_by TEXT NOT NULL,
    proposal_reason TEXT NOT NULL,
    confirmed_by TEXT,
    confirmation_reason TEXT,
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT delivery_appointment_window_valid
        CHECK (proposed_end_at > proposed_start_at),
    CONSTRAINT delivery_appointment_status_valid
        CHECK (status IN ('proposed', 'confirmed')),
    CONSTRAINT delivery_appointment_proposer_nonempty
        CHECK (length(trim(proposed_by)) > 0),
    CONSTRAINT delivery_appointment_proposal_reason_nonempty
        CHECK (length(trim(proposal_reason)) > 0),
    CONSTRAINT delivery_appointment_confirmation_consistency
        CHECK (
            (
                status = 'proposed'
                AND confirmed_by IS NULL
                AND confirmation_reason IS NULL
                AND confirmed_at IS NULL
            )
            OR
            (
                status = 'confirmed'
                AND confirmed_by IS NOT NULL
                AND length(trim(confirmed_by)) > 0
                AND confirmation_reason IS NOT NULL
                AND length(trim(confirmation_reason)) > 0
                AND confirmed_at IS NOT NULL
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_service_delivery_appointments_provider
    ON service_delivery_appointments(provider_id);
