CREATE TABLE IF NOT EXISTS service_review_requests (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    satisfaction_follow_up_id UUID NOT NULL UNIQUE
        REFERENCES service_satisfaction_followups(id) ON DELETE CASCADE,
    provider_id UUID NOT NULL
        REFERENCES providers(id) ON DELETE RESTRICT,
    purpose TEXT NOT NULL DEFAULT 'public_review_request',
    message TEXT NOT NULL,
    target_platform TEXT,
    target_url TEXT,
    destination_channel TEXT,
    destination_address TEXT,
    status TEXT NOT NULL DEFAULT 'prepared',
    prepared_reason TEXT NOT NULL,
    prepared_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT review_request_purpose_valid
        CHECK (purpose = 'public_review_request'),
    CONSTRAINT review_request_message_nonempty
        CHECK (length(trim(message)) > 0),
    CONSTRAINT review_request_status_valid
        CHECK (status = 'prepared'),
    CONSTRAINT review_request_reason_nonempty
        CHECK (length(trim(prepared_reason)) > 0),
    CONSTRAINT review_request_preparer_nonempty
        CHECK (length(trim(prepared_by)) > 0),
    CONSTRAINT review_request_target_unresolved
        CHECK (
            target_platform IS NULL
            AND target_url IS NULL
        ),
    CONSTRAINT review_request_destination_unresolved
        CHECK (
            destination_channel IS NULL
            AND destination_address IS NULL
        )
);

CREATE INDEX IF NOT EXISTS idx_service_review_requests_provider
    ON service_review_requests(provider_id);
