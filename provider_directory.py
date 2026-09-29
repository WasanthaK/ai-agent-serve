"""Deterministic provider-directory persistence for Phase 5.

This module stores provider identity and approval state only. It does not perform
routing, capability matching, onboarding, or approval authorization.
"""

import uuid

from psycopg.rows import dict_row

from db import get_connection


APPROVAL_STATUSES = frozenset({
    "pending",
    "approved",
    "suspended",
    "rejected",
})


class ProviderDirectoryValidationError(ValueError):
    """Provider directory input is invalid before persistence."""


def normalize_provider_display_name(value: str) -> str:
    if not isinstance(value, str):
        raise ProviderDirectoryValidationError("Provider display name must be text")

    normalized = value.strip()
    if not normalized:
        raise ProviderDirectoryValidationError("Provider display name is required")
    if len(normalized) > 200:
        raise ProviderDirectoryValidationError(
            "Provider display name must be at most 200 characters"
        )
    return normalized


def validate_approval_status(value: str) -> str:
    if value not in APPROVAL_STATUSES:
        raise ProviderDirectoryValidationError(
            f"Unsupported provider approval status: {value}"
        )
    return value


def create_provider(
    display_name: str,
    *,
    approval_status: str = "pending",
    provider_id=None,
):
    """Persist provider identity and current approval state.

    Application-level authorization for creating or approving a provider belongs
    outside this repository function. No model output should call this function
    directly as an authority decision.
    """

    provider_id = provider_id or uuid.uuid4()
    display_name = normalize_provider_display_name(display_name)
    approval_status = validate_approval_status(approval_status)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO providers (
                    id,
                    display_name,
                    approval_status
                )
                VALUES (%s, %s, %s)
                RETURNING *
                """,
                (provider_id, display_name, approval_status),
            )
            return cur.fetchone()


def get_provider(provider_id):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM providers
                WHERE id = %s
                """,
                (provider_id,),
            )
            return cur.fetchone()


def list_providers(*, approval_status=None):
    if approval_status is not None:
        approval_status = validate_approval_status(approval_status)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if approval_status is None:
                cur.execute(
                    """
                    SELECT *
                    FROM providers
                    ORDER BY created_at ASC, id ASC
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM providers
                    WHERE approval_status = %s
                    ORDER BY created_at ASC, id ASC
                    """,
                    (approval_status,),
                )
            return cur.fetchall()


def list_approved_providers():
    """Return only providers deterministically marked approved in persisted state."""

    return list_providers(approval_status="approved")
