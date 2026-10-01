"""Deterministic provider invitation and onboarding persistence for Phase 5A.

Invitation secrets are generated with a cryptographically secure random source and only
SHA-256 hashes are persisted. Onboarding completion never grants provider approval,
compliance, routing, or other authority.
"""

from datetime import datetime, timezone
import hashlib
import secrets
import uuid

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from db import get_connection


INVITATION_STATUSES = frozenset({"pending", "accepted", "revoked", "expired"})
ONBOARDING_STATUSES = frozenset({
    "not_started",
    "in_progress",
    "submitted",
    "completed",
})
ONBOARDING_TRANSITIONS = {
    "not_started": frozenset({"in_progress"}),
    "in_progress": frozenset({"submitted"}),
    "submitted": frozenset({"completed"}),
    "completed": frozenset(),
}


class ProviderOnboardingValidationError(ValueError):
    """Provider onboarding input is invalid before persistence."""


class ProviderOnboardingConflictError(RuntimeError):
    """Requested invitation or onboarding transition conflicts with persisted state."""


class ProviderInvitationInvalidError(RuntimeError):
    """Invitation secret cannot authorize onboarding acceptance."""


def _hash_invitation_secret(secret: str) -> str:
    if not isinstance(secret, str) or not secret or len(secret) > 512:
        raise ProviderOnboardingValidationError("Invitation secret is invalid")
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _validate_expires_at(expires_at: datetime) -> datetime:
    if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
        raise ProviderOnboardingValidationError(
            "Invitation expiry must be a timezone-aware datetime"
        )
    if expires_at <= datetime.now(timezone.utc):
        raise ProviderOnboardingValidationError("Invitation expiry must be in the future")
    return expires_at


def validate_onboarding_status(status: str) -> str:
    if status not in ONBOARDING_STATUSES:
        raise ProviderOnboardingValidationError(
            f"Unsupported provider onboarding status: {status}"
        )
    return status


def create_provider_invitation(provider_id, expires_at: datetime):
    """Create one pending invitation and return its secret exactly once.

    Stale pending invitations for the provider are marked expired first. The raw
    secret is never persisted. Callers must treat the returned secret as sensitive
    and must not place it in logs, events, or analytics.
    """

    expires_at = _validate_expires_at(expires_at)
    invitation_id = uuid.uuid4()
    secret = secrets.token_urlsafe(32)
    token_hash = _hash_invitation_secret(secret)

    try:
        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE provider_invitations
                    SET invitation_status = 'expired', updated_at = NOW()
                    WHERE provider_id = %s
                      AND invitation_status = 'pending'
                      AND expires_at <= NOW()
                    """,
                    (provider_id,),
                )
                cur.execute(
                    """
                    INSERT INTO provider_invitations (
                        id,
                        provider_id,
                        token_hash,
                        expires_at
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, provider_id, invitation_status, expires_at,
                              accepted_at, created_at, updated_at
                    """,
                    (invitation_id, provider_id, token_hash, expires_at),
                )
                invitation = cur.fetchone()
                cur.execute(
                    """
                    INSERT INTO provider_onboarding (provider_id, onboarding_status)
                    VALUES (%s, 'not_started')
                    ON CONFLICT (provider_id) DO NOTHING
                    """,
                    (provider_id,),
                )
    except UniqueViolation as exc:
        raise ProviderOnboardingConflictError(
            "Provider already has a pending invitation"
        ) from exc

    return {"invitation": invitation, "secret": secret}


def get_provider_onboarding(provider_id):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT provider_id, onboarding_status, updated_at
                FROM provider_onboarding
                WHERE provider_id = %s
                """,
                (provider_id,),
            )
            return cur.fetchone()


def accept_provider_invitation(secret: str):
    """Accept a non-expired pending invitation and start onboarding.

    Repeating acceptance with the same already-accepted secret is idempotent.
    Expired or revoked invitations fail closed. Expiry is committed before an
    expired-invitation error is raised so a replacement invite is not blocked.
    """

    token_hash = _hash_invitation_secret(secret)
    invalid_reason = None
    onboarding = None

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE provider_invitations
                SET invitation_status = 'accepted',
                    accepted_at = NOW(),
                    updated_at = NOW()
                WHERE token_hash = %s
                  AND invitation_status = 'pending'
                  AND expires_at > NOW()
                RETURNING id, provider_id, invitation_status, expires_at,
                          accepted_at, created_at, updated_at
                """,
                (token_hash,),
            )
            invitation = cur.fetchone()

            if invitation is None:
                cur.execute(
                    """
                    SELECT id, provider_id, invitation_status, expires_at,
                           accepted_at, created_at, updated_at
                    FROM provider_invitations
                    WHERE token_hash = %s
                    """,
                    (token_hash,),
                )
                invitation = cur.fetchone()

                if invitation is None:
                    invalid_reason = "Invitation is invalid"
                elif invitation["invitation_status"] == "accepted":
                    pass
                elif (
                    invitation["invitation_status"] == "pending"
                    and invitation["expires_at"] <= datetime.now(timezone.utc)
                ):
                    cur.execute(
                        """
                        UPDATE provider_invitations
                        SET invitation_status = 'expired', updated_at = NOW()
                        WHERE id = %s AND invitation_status = 'pending'
                        """,
                        (invitation["id"],),
                    )
                    invalid_reason = "Invitation has expired"
                else:
                    invalid_reason = "Invitation is not active"

            if invalid_reason is None:
                cur.execute(
                    """
                    INSERT INTO provider_onboarding (provider_id, onboarding_status)
                    VALUES (%s, 'in_progress')
                    ON CONFLICT (provider_id) DO UPDATE
                    SET onboarding_status = 'in_progress', updated_at = NOW()
                    WHERE provider_onboarding.onboarding_status = 'not_started'
                    """,
                    (invitation["provider_id"],),
                )
                cur.execute(
                    """
                    SELECT provider_id, onboarding_status, updated_at
                    FROM provider_onboarding
                    WHERE provider_id = %s
                    """,
                    (invitation["provider_id"],),
                )
                onboarding = cur.fetchone()

    if invalid_reason is not None:
        raise ProviderInvitationInvalidError(invalid_reason)

    return {"invitation": invitation, "onboarding": onboarding}


def revoke_provider_invitation(invitation_id):
    """Revoke a pending invitation without changing provider authority."""

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE provider_invitations
                SET invitation_status = 'revoked', updated_at = NOW()
                WHERE id = %s AND invitation_status = 'pending'
                RETURNING id, provider_id, invitation_status, expires_at,
                          accepted_at, created_at, updated_at
                """,
                (invitation_id,),
            )
            revoked = cur.fetchone()
            if revoked is not None:
                return revoked

            cur.execute(
                """
                SELECT id, provider_id, invitation_status, expires_at,
                       accepted_at, created_at, updated_at
                FROM provider_invitations
                WHERE id = %s
                """,
                (invitation_id,),
            )
            invitation = cur.fetchone()
            if invitation is None:
                raise ProviderOnboardingConflictError("Invitation does not exist")
            if invitation["invitation_status"] == "revoked":
                return invitation
            raise ProviderOnboardingConflictError(
                "Only pending invitations can be revoked"
            )


def advance_provider_onboarding(provider_id, target_status: str):
    """Advance onboarding through the explicit lifecycle one step at a time.

    Completing onboarding does not alter provider approval or compliance status.
    """

    target_status = validate_onboarding_status(target_status)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT provider_id, onboarding_status, updated_at
                FROM provider_onboarding
                WHERE provider_id = %s
                FOR UPDATE
                """,
                (provider_id,),
            )
            current = cur.fetchone()
            if current is None:
                raise ProviderOnboardingConflictError("Onboarding is not initialized")

            current_status = current["onboarding_status"]
            if target_status == current_status:
                return current
            if target_status not in ONBOARDING_TRANSITIONS[current_status]:
                raise ProviderOnboardingConflictError(
                    f"Invalid onboarding transition: {current_status} -> {target_status}"
                )

            cur.execute(
                """
                UPDATE provider_onboarding
                SET onboarding_status = %s, updated_at = NOW()
                WHERE provider_id = %s
                RETURNING provider_id, onboarding_status, updated_at
                """,
                (target_status, provider_id),
            )
            return cur.fetchone()
