CREATE TABLE IF NOT EXISTS provider_onboarding (
    provider_id UUID PRIMARY KEY REFERENCES providers(id) ON DELETE CASCADE,
    onboarding_status TEXT NOT NULL DEFAULT 'not_started',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT provider_onboarding_status_valid
        CHECK (onboarding_status IN ('not_started', 'in_progress', 'submitted', 'completed'))
);

CREATE TABLE IF NOT EXISTS provider_invitations (
    id UUID PRIMARY KEY,
    provider_id UUID NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    invitation_status TEXT NOT NULL DEFAULT 'pending',
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT provider_invitation_status_valid
        CHECK (invitation_status IN ('pending', 'accepted', 'revoked', 'expired'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_invitations_one_pending
    ON provider_invitations (provider_id)
    WHERE invitation_status = 'pending';

CREATE INDEX IF NOT EXISTS idx_provider_invitations_provider
    ON provider_invitations (provider_id, created_at DESC);
