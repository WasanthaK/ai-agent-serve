ALTER TABLE service_satisfaction_followups
    ADD COLUMN IF NOT EXISTS rating INTEGER,
    ADD COLUMN IF NOT EXISTS comment TEXT,
    ADD COLUMN IF NOT EXISTS responded_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS response_source TEXT,
    ADD COLUMN IF NOT EXISTS response_recorded_by TEXT;

ALTER TABLE service_satisfaction_followups
    DROP CONSTRAINT IF EXISTS satisfaction_followup_status_valid;

ALTER TABLE service_satisfaction_followups
    ADD CONSTRAINT satisfaction_followup_status_valid
        CHECK (status IN ('prepared', 'responded'));

ALTER TABLE service_satisfaction_followups
    ADD CONSTRAINT satisfaction_followup_response_consistency
        CHECK (
            (
                status = 'prepared'
                AND rating IS NULL
                AND comment IS NULL
                AND responded_at IS NULL
                AND response_source IS NULL
                AND response_recorded_by IS NULL
            )
            OR
            (
                status = 'responded'
                AND rating BETWEEN 1 AND 5
                AND responded_at IS NOT NULL
                AND response_source IS NOT NULL
                AND length(trim(response_source)) > 0
                AND response_recorded_by IS NOT NULL
                AND length(trim(response_recorded_by)) > 0
            )
        );
