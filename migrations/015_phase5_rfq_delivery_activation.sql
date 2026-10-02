ALTER TABLE rfq_provider_handoffs
    DROP CONSTRAINT IF EXISTS rfq_provider_handoff_status_prepared_only;

ALTER TABLE rfq_provider_handoffs
    ADD COLUMN IF NOT EXISTS authorized_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS authorized_by TEXT,
    ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS response_deadline_at TIMESTAMPTZ;

ALTER TABLE rfq_provider_handoffs
    DROP CONSTRAINT IF EXISTS rfq_provider_handoff_status_valid;

ALTER TABLE rfq_provider_handoffs
    ADD CONSTRAINT rfq_provider_handoff_status_valid
        CHECK (status IN ('prepared', 'authorized', 'delivered'));

ALTER TABLE rfq_provider_handoffs
    DROP CONSTRAINT IF EXISTS rfq_provider_handoff_delivery_timing_valid;

ALTER TABLE rfq_provider_handoffs
    ADD CONSTRAINT rfq_provider_handoff_delivery_timing_valid
        CHECK (
            (status = 'prepared'
                AND authorized_at IS NULL
                AND authorized_by IS NULL
                AND delivered_at IS NULL
                AND response_deadline_at IS NULL)
            OR
            (status = 'authorized'
                AND authorized_at IS NOT NULL
                AND authorized_by IS NOT NULL
                AND delivered_at IS NULL
                AND response_deadline_at IS NULL)
            OR
            (status = 'delivered'
                AND authorized_at IS NOT NULL
                AND authorized_by IS NOT NULL
                AND delivered_at IS NOT NULL
                AND response_deadline_at IS NOT NULL
                AND response_deadline_at > delivered_at)
        );

CREATE INDEX IF NOT EXISTS idx_rfq_provider_handoffs_status
    ON rfq_provider_handoffs(status);
