CREATE TABLE IF NOT EXISTS service_delivery_notifications (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    delivery_handoff_id UUID NOT NULL
        REFERENCES service_delivery_handoffs(id) ON DELETE CASCADE,
    audience_type TEXT NOT NULL,
    provider_id UUID
        REFERENCES providers(id) ON DELETE RESTRICT,
    purpose TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    destination_channel TEXT,
    destination_address TEXT,
    status TEXT NOT NULL DEFAULT 'prepared',
    prepared_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT delivery_notification_audience_valid
        CHECK (audience_type IN ('customer', 'provider')),
    CONSTRAINT delivery_notification_status_valid
        CHECK (status = 'prepared'),
    CONSTRAINT delivery_notification_purpose_nonempty
        CHECK (length(trim(purpose)) > 0),
    CONSTRAINT delivery_notification_subject_nonempty
        CHECK (length(trim(subject)) > 0),
    CONSTRAINT delivery_notification_body_nonempty
        CHECK (length(trim(body)) > 0),
    CONSTRAINT delivery_notification_actor_nonempty
        CHECK (length(trim(prepared_by)) > 0),
    CONSTRAINT delivery_notification_provider_consistency
        CHECK (
            (audience_type = 'customer' AND provider_id IS NULL)
            OR
            (audience_type = 'provider' AND provider_id IS NOT NULL)
        ),
    CONSTRAINT delivery_notification_destination_unresolved
        CHECK (
            destination_channel IS NULL
            AND destination_address IS NULL
        ),
    UNIQUE (request_id, audience_type)
);

CREATE INDEX IF NOT EXISTS idx_service_delivery_notifications_handoff
    ON service_delivery_notifications(delivery_handoff_id);
