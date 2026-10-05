"""Durable tenant identity foundation for Phase 8.

This module owns tenant identity and lifecycle facts only. It deliberately does
not bind requests, providers, credentials, skills, or policies to tenants yet,
and therefore must not be treated as multi-tenant isolation by itself.
"""

import re
import uuid

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from db import get_connection


TENANT_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
TENANT_STATUSES = frozenset({
    "pending",
    "active",
    "suspended",
    "closed",
})
TENANT_TRANSITIONS = {
    "pending": frozenset({"active", "closed"}),
    "active": frozenset({"suspended", "closed"}),
    "suspended": frozenset({"active", "closed"}),
    "closed": frozenset(),
}


class TenantValidationError(ValueError):
    pass


class TenantNotFoundError(LookupError):
    pass


class TenantStateError(RuntimeError):
    pass


class TenantConflictError(RuntimeError):
    pass


def _normalize_tenant_key(value):
    if not isinstance(value, str):
        raise TenantValidationError("tenant_key must be text")
    if not TENANT_KEY_PATTERN.fullmatch(value):
        raise TenantValidationError(
            "tenant_key must be canonical lowercase letters, digits or hyphens"
        )
    return value


def _normalize_display_name(value):
    if not isinstance(value, str):
        raise TenantValidationError("display_name must be text")
    value = value.strip()
    if not value:
        raise TenantValidationError("display_name is required")
    if len(value) > 200:
        raise TenantValidationError("display_name is too long")
    return value


def _normalize_status(value):
    if not isinstance(value, str) or value not in TENANT_STATUSES:
        raise TenantValidationError("Unknown tenant status")
    return value


def _normalize_actor(value):
    if not isinstance(value, str):
        raise TenantValidationError("actor must be text")
    value = value.strip()
    if not value:
        raise TenantValidationError("actor is required")
    if len(value) > 200:
        raise TenantValidationError("actor is too long")
    return value


def _normalize_reason(value):
    if not isinstance(value, str):
        raise TenantValidationError("reason must be text")
    value = value.strip()
    if not value:
        raise TenantValidationError("reason is required")
    if len(value) > 2000:
        raise TenantValidationError("reason is too long")
    return value


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise TenantValidationError(f"{field_name} must be a UUID")
    return value


def _record_tenant_event(cur, *, tenant_id, event_type, actor, details):
    event_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO platform_tenant_events (
            id,
            tenant_id,
            event_type,
            actor,
            details
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            event_id,
            tenant_id,
            event_type,
            actor,
            Jsonb(details),
        ),
    )
    return event_id


def create_tenant(
    tenant_key,
    display_name,
    *,
    tenant_id=None,
    actor="system:bootstrap",
):
    tenant_key = _normalize_tenant_key(tenant_key)
    display_name = _normalize_display_name(display_name)
    actor = _normalize_actor(actor)
    tenant_id = tenant_id or uuid.uuid4()
    _validate_uuid(tenant_id, "tenant_id")

    try:
        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO platform_tenants (
                        id,
                        tenant_key,
                        display_name
                    )
                    VALUES (%s, %s, %s)
                    RETURNING *
                    """,
                    (tenant_id, tenant_key, display_name),
                )
                created = cur.fetchone()
                _record_tenant_event(
                    cur,
                    tenant_id=tenant_id,
                    event_type="tenant_created",
                    actor=actor,
                    details={
                        "tenant_key": tenant_key,
                        "status": "pending",
                    },
                )
                return created
    except UniqueViolation as exc:
        raise TenantConflictError(
            "Tenant id or tenant_key already exists"
        ) from exc


def get_tenant(tenant_id):
    tenant_id = _validate_uuid(tenant_id, "tenant_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM platform_tenants
                WHERE id = %s
                """,
                (tenant_id,),
            )
            return cur.fetchone()


def get_tenant_by_key(tenant_key):
    tenant_key = _normalize_tenant_key(tenant_key)
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM platform_tenants
                WHERE tenant_key = %s
                """,
                (tenant_key,),
            )
            return cur.fetchone()


def list_tenants(*, status=None):
    if status is not None:
        status = _normalize_status(status)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if status is None:
                cur.execute(
                    """
                    SELECT *
                    FROM platform_tenants
                    ORDER BY created_at ASC, id ASC
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM platform_tenants
                    WHERE status = %s
                    ORDER BY created_at ASC, id ASC
                    """,
                    (status,),
                )
            return cur.fetchall()


def set_tenant_status(
    tenant_id,
    new_status,
    *,
    actor,
    reason,
):
    tenant_id = _validate_uuid(tenant_id, "tenant_id")
    new_status = _normalize_status(new_status)
    actor = _normalize_actor(actor)
    reason = _normalize_reason(reason)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM platform_tenants
                WHERE id = %s
                FOR UPDATE
                """,
                (tenant_id,),
            )
            existing = cur.fetchone()
            if existing is None:
                raise TenantNotFoundError("Tenant not found")

            current_status = existing["status"]
            if new_status == current_status:
                return existing

            if new_status not in TENANT_TRANSITIONS[current_status]:
                raise TenantStateError(
                    f"Tenant cannot transition from {current_status} to {new_status}"
                )

            cur.execute(
                """
                UPDATE platform_tenants
                SET status = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (new_status, tenant_id),
            )
            updated = cur.fetchone()

            _record_tenant_event(
                cur,
                tenant_id=tenant_id,
                event_type="tenant_status_changed",
                actor=actor,
                details={
                    "previous_status": current_status,
                    "new_status": new_status,
                    "reason": reason,
                },
            )
            return updated


def get_tenant_events(tenant_id):
    tenant_id = _validate_uuid(tenant_id, "tenant_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM platform_tenant_events
                WHERE tenant_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (tenant_id,),
            )
            return cur.fetchall()
