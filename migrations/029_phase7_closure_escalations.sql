CREATE TABLE IF NOT EXISTS service_closure_escalations (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    satisfaction_follow_up_id UUID NOT NULL
        REFERENCES service_satisfaction_followups(id) ON DELETE CASCADE,
    provider_id UUID NOT NULL
        REFERENCES providers(id) ON DELETE RESTRICT,
    escalation_kind TEXT NOT NULL,
    priority TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT closure_escalation_kind_valid
        CHECK (escalation_kind IN ('complaint', 'rework')),
    CONSTRAINT closure_escalation_priority_valid
        CHECK (priority IN ('normal', 'high', 'urgent')),
    CONSTRAINT closure_escalation_reason_nonempty
        CHECK (length(trim(reason)) > 0),
    CONSTRAINT closure_escalation_status_valid
        CHECK (status = 'open'),
    CONSTRAINT closure_escalation_creator_nonempty
        CHECK (length(trim(created_by)) > 0),
    CONSTRAINT closure_escalation_request_kind_unique
        UNIQUE (request_id, escalation_kind)
);

CREATE INDEX IF NOT EXISTS idx_service_closure_escalations_request
    ON service_closure_escalations(request_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_service_closure_escalations_provider
    ON service_closure_escalations(provider_id, escalation_kind, created_at);
