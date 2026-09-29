CREATE TABLE IF NOT EXISTS providers (
    id UUID PRIMARY KEY,
    display_name TEXT NOT NULL,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT providers_display_name_not_blank
        CHECK (BTRIM(display_name) <> ''),
    CONSTRAINT providers_display_name_length
        CHECK (CHAR_LENGTH(display_name) <= 200),
    CONSTRAINT providers_approval_status_valid
        CHECK (approval_status IN ('pending', 'approved', 'suspended', 'rejected'))
);

CREATE INDEX IF NOT EXISTS idx_providers_approval_status
    ON providers (approval_status);
