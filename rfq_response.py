"""Governed provider-response ingestion for delivered RFQ handoffs.

This module records structured quote/decline outcomes only. It performs no
provider contact, ranking, quote evaluation, dispatch, or external network action.
"""

from datetime import datetime
import uuid

from psycopg.rows import dict_row

from db import get_connection, record_event_in_transaction
from provider_response_reliability import RESPONSE_KINDS


class RFQResponseValidationError(ValueError):
    """Provider-response input is invalid before persistence."""


class RFQResponseNotFoundError(LookupError):
    """The request/RFQ handoff does not exist."""


class RFQResponseStateError(RuntimeError):
    """The RFQ handoff is not eligible for response ingestion."""


class RFQResponseConflictError(RuntimeError):
    """The response conflicts with immutable response evidence."""


def _validate_uuid(value, field_name: str):
    if not isinstance(value, uuid.UUID):
        raise RFQResponseValidationError(f"{field_name} must be a UUID")
    return value


def _validate_timestamp(value) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RFQResponseValidationError(
            "responded_at must be a timezone-aware datetime"
        )
    return value


def _normalize_actor(actor: str) -> str:
    if not isinstance(actor, str):
        raise RFQResponseValidationError("actor must be text")
    normalized = actor.strip()
    if not normalized:
        raise RFQResponseValidationError("actor is required")
    if len(normalized) > 200:
        raise RFQResponseValidationError("actor is too long")
    if not normalized.startswith("operator:"):
        raise RFQResponseValidationError(
            "Provider-response ingestion authority must be an operator"
        )
    return normalized


def ingest_rfq_response(
    request_id,
    handoff_id,
    response_kind: str,
    responded_at: datetime,
    *,
    actor: str,
):
    """Record one immutable quote/decline outcome for a delivered handoff."""

    request_id = _validate_uuid(request_id, "request_id")
    handoff_id = _validate_uuid(handoff_id, "handoff_id")
    responded_at = _validate_timestamp(responded_at)
    actor = _normalize_actor(actor)

    if response_kind not in RESPONSE_KINDS:
        raise RFQResponseValidationError(
            f"Unsupported provider response kind: {response_kind}"
        )

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT h.id, h.rfq_id, h.provider_id, h.status, h.delivered_at
                FROM rfq_provider_handoffs h
                INNER JOIN rfqs r ON r.id = h.rfq_id
                WHERE r.request_id = %s
                  AND h.id = %s
                FOR UPDATE OF h, r
                """,
                (request_id, handoff_id),
            )
            handoff = cur.fetchone()
            if handoff is None:
                raise RFQResponseNotFoundError("RFQ provider handoff not found")
            if handoff["status"] != "delivered":
                raise RFQResponseStateError(
                    "Provider response requires a delivered RFQ handoff"
                )
            if responded_at < handoff["delivered_at"]:
                raise RFQResponseValidationError(
                    "responded_at cannot be before RFQ delivery"
                )

            response_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO provider_response_events (
                    id, provider_id, opportunity_id, response_kind, responded_at
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (provider_id, opportunity_id) DO NOTHING
                RETURNING id, provider_id, opportunity_id, response_kind,
                          responded_at, created_at
                """,
                (
                    response_id,
                    handoff["provider_id"],
                    handoff_id,
                    response_kind,
                    responded_at,
                ),
            )
            response = cur.fetchone()

            if response is None:
                cur.execute(
                    """
                    SELECT id, provider_id, opportunity_id, response_kind,
                           responded_at, created_at
                    FROM provider_response_events
                    WHERE provider_id = %s AND opportunity_id = %s
                    """,
                    (handoff["provider_id"], handoff_id),
                )
                response = cur.fetchone()
                if (
                    response["response_kind"] != response_kind
                    or response["responded_at"] != responded_at
                ):
                    raise RFQResponseConflictError(
                        "Provider response already exists with different evidence"
                    )
                created = False
            else:
                created = True

            if created:
                record_event_in_transaction(
                    cur,
                    request_id=request_id,
                    event_type="rfq_provider_response_recorded",
                    actor=actor,
                    details={
                        "rfq_id": str(handoff["rfq_id"]),
                        "handoff_id": str(handoff_id),
                        "provider_id": str(handoff["provider_id"]),
                        "response_kind": response_kind,
                        "responded_at": responded_at.isoformat(),
                    },
                )

            return {
                "response_id": str(response["id"]),
                "handoff_id": str(handoff_id),
                "provider_id": str(response["provider_id"]),
                "response_kind": response["response_kind"],
                "responded_at": response["responded_at"],
                "created_at": response["created_at"],
            }
