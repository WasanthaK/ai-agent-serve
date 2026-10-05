CREATE TABLE IF NOT EXISTS service_satisfaction_followups (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    delivery_status_id UUID NOT NULL UNIQUE
        REFERENCES service_delivery_status(id) ON DELETE CASCADE,
    provider_id UUID NOT NULL
        REFERENCES providers(id) ON DELETE RESTRICT,
    purpose TEXT NOT NULL DEFAULT 'customer_satisfaction',
    question TEXT NOT NULL,
    rating_min INTEGER NOT NULL DEFAULT 1,
    rating_max INTEGER NOT NULL DEFAULT 5,
    destination_channel TEXT,
    destination_address TEXT,
    status TEXT NOT NULL DEFAULT 'prepared',
    prepared_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT satisfaction_followup_purpose_valid
        CHECK (purpose = 'customer_satisfaction'),
    CONSTRAINT satisfaction_followup_question_nonempty
        CHECK (length(trim(question)) > 0),
    CONSTRAINT satisfaction_followup_rating_scale_valid
        CHECK (rating_min = 1 AND rating_max = 5),
    CONSTRAINT satisfaction_followup_status_valid
        CHECK (status = 'prepared'),
    CONSTRAINT satisfaction_followup_preparer_nonempty
        CHECK (length(trim(prepared_by)) > 0),
    CONSTRAINT satisfaction_followup_destination_unresolved
        CHECK (
            destination_channel IS NULL
            AND destination_address IS NULL
        )
);

CREATE INDEX IF NOT EXISTS idx_service_satisfaction_followups_provider
    ON service_satisfaction_followups(provider_id);
