"""Post-award internal delivery handoff.

Creates one immutable service-delivery snapshot from a human quote award and
atomically transitions the request to the existing actioned state. No external
message, appointment, dispatch, or provider contact is performed.
"""

import uuid

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from db import get_connection, record_event_in_transaction


ACTIVATABLE_REQUEST_STATUSES = frozenset({"ready", "approved"})


class DeliveryHandoffValidationError(ValueError):
    pass


class DeliveryHandoffNotFoundError(LookupError):
    pass


class DeliveryHandoffStateError(RuntimeError):
    pass


class DeliveryHandoffConflictError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise DeliveryHandoffValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise DeliveryHandoffValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise DeliveryHandoffValidationError("actor is required")
    if len(actor) > 200:
        raise DeliveryHandoffValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise DeliveryHandoffValidationError(
            "Delivery handoff authority must be an operator"
        )
    return actor


def _result(row):
    return {
        "delivery_handoff_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "award_id": str(row["award_id"]),
        "normalized_quote_id": str(row["normalized_quote_id"]),
        "provider_id": str(row["provider_id"]),
        "amount_minor": row["amount_minor"],
        "currency": row["currency"].strip(),
        "scope_summary": row["scope_summary"],
        "exclusions": list(row["exclusions"]),
        "terms": list(row["terms"]),
        "available_from": row["available_from"],
        "estimated_duration_days": row["estimated_duration_days"],
        "activated_by": row["activated_by"],
        "created_at": row["created_at"],
        "request_status": "actioned",
        "provider_contacted": False,
        "dispatch_created": False,
        "appointment_created": False,
    }


def get_delivery_handoff(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_delivery_handoffs
                WHERE request_id = %s
                """,
                (request_id,),
            )
            row = cur.fetchone()
            return None if row is None else _result(row)


def activate_delivery_handoff(request_id, award_id, *, actor):
    request_id = _validate_uuid(request_id, "request_id")
    award_id = _validate_uuid(award_id, "award_id")
    actor = _normalize_actor(actor)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, status
                FROM agent_requests
                WHERE id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            request = cur.fetchone()
            if request is None:
                raise DeliveryHandoffNotFoundError("Request not found")

            cur.execute(
                """
                SELECT *
                FROM service_delivery_handoffs
                WHERE request_id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                result = _result(existing)
                if (
                    existing["award_id"] == award_id
                    and existing["activated_by"] == actor
                ):
                    return result
                raise DeliveryHandoffConflictError(
                    "A different delivery handoff already exists"
                )

            if request["status"] not in ACTIVATABLE_REQUEST_STATUSES:
                raise DeliveryHandoffStateError(
                    "Delivery handoff requires request status ready or approved"
                )

            cur.execute(
                """
                SELECT
                    a.id AS award_id,
                    a.normalized_quote_id,
                    a.provider_id,
                    q.amount_minor,
                    q.currency,
                    q.scope_summary,
                    q.exclusions,
                    q.terms,
                    q.available_from,
                    q.estimated_duration_days
                FROM quote_awards a
                INNER JOIN normalized_provider_quotes q
                    ON q.id = a.normalized_quote_id
                WHERE a.request_id = %s
                  AND a.id = %s
                FOR UPDATE OF a, q
                """,
                (request_id, award_id),
            )
            award = cur.fetchone()
            if award is None:
                raise DeliveryHandoffNotFoundError(
                    "Quote award not found for request"
                )

            handoff_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO service_delivery_handoffs (
                    id,
                    request_id,
                    award_id,
                    normalized_quote_id,
                    provider_id,
                    amount_minor,
                    currency,
                    scope_summary,
                    exclusions,
                    terms,
                    available_from,
                    estimated_duration_days,
                    activated_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    handoff_id,
                    request_id,
                    award["award_id"],
                    award["normalized_quote_id"],
                    award["provider_id"],
                    award["amount_minor"],
                    award["currency"],
                    award["scope_summary"],
                    Jsonb(list(award["exclusions"])),
                    Jsonb(list(award["terms"])),
                    award["available_from"],
                    award["estimated_duration_days"],
                    actor,
                ),
            )
            created = cur.fetchone()

            cur.execute(
                """
                UPDATE agent_requests
                SET status = 'actioned',
                    actioned_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (request_id,),
            )

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="delivery_handoff_activated",
                actor=actor,
                details={
                    "delivery_handoff_id": str(handoff_id),
                    "award_id": str(award["award_id"]),
                    "normalized_quote_id": str(
                        award["normalized_quote_id"]
                    ),
                    "provider_id": str(award["provider_id"]),
                    "previous_status": request["status"],
                    "new_status": "actioned",
                    "provider_contacted": False,
                    "dispatch_created": False,
                    "appointment_created": False,
                },
            )

            return _result(created)
