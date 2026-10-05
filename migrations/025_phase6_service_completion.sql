ALTER TABLE service_delivery_status
    ADD COLUMN IF NOT EXISTS completed_by TEXT,
    ADD COLUMN IF NOT EXISTS completion_reason TEXT,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

ALTER TABLE service_delivery_status
    DROP CONSTRAINT IF EXISTS delivery_status_valid;

ALTER TABLE service_delivery_status
    ADD CONSTRAINT delivery_status_valid
        CHECK (status IN ('scheduled', 'in_progress', 'completed'));

ALTER TABLE service_delivery_status
    DROP CONSTRAINT IF EXISTS delivery_status_start_consistency;

ALTER TABLE service_delivery_status
    ADD CONSTRAINT delivery_status_start_consistency
        CHECK (
            (
                status = 'scheduled'
                AND started_by IS NULL
                AND start_reason IS NULL
                AND started_at IS NULL
                AND completed_by IS NULL
                AND completion_reason IS NULL
                AND completed_at IS NULL
            )
            OR
            (
                status = 'in_progress'
                AND started_by IS NOT NULL
                AND length(trim(started_by)) > 0
                AND start_reason IS NOT NULL
                AND length(trim(start_reason)) > 0
                AND started_at IS NOT NULL
                AND completed_by IS NULL
                AND completion_reason IS NULL
                AND completed_at IS NULL
            )
            OR
            (
                status = 'completed'
                AND started_by IS NOT NULL
                AND length(trim(started_by)) > 0
                AND start_reason IS NOT NULL
                AND length(trim(start_reason)) > 0
                AND started_at IS NOT NULL
                AND completed_by IS NOT NULL
                AND length(trim(completed_by)) > 0
                AND completion_reason IS NOT NULL
                AND length(trim(completion_reason)) > 0
                AND completed_at IS NOT NULL
            )
        );
