CREATE TABLE IF NOT EXISTS service_delivery_exceptions (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    delivery_status_id UUID NOT NULL
        REFERENCES service_delivery_status(id) ON DELETE CASCADE,
    provider_id UUID NOT NULL
        REFERENCES providers(id) ON DELETE RESTRICT,
    exception_kind TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    summary TEXT NOT NULL,
    expected_resolution_at TIMESTAMPTZ,
    recorded_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT delivery_exception_kind_valid
        CHECK (exception_kind IN ('delay', 'service_issue')),
    CONSTRAINT delivery_exception_summary_nonempty
        CHECK (length(trim(summary)) > 0),
    CONSTRAINT delivery_exception_recorder_nonempty
        CHECK (length(trim(recorded_by)) > 0),
    CONSTRAINT delivery_exception_expected_resolution_valid
        CHECK (
            expected_resolution_at IS NULL
            OR expected_resolution_at > occurred_at
        )
);

CREATE INDEX IF NOT EXISTS idx_service_delivery_exceptions_request
    ON service_delivery_exceptions(request_id, occurred_at);

CREATE INDEX IF NOT EXISTS idx_service_delivery_exceptions_status
    ON service_delivery_exceptions(delivery_status_id, occurred_at);
