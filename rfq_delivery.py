"""RFQ delivery authorization and response-opportunity activation.

This module manages software-only delivery state. It does not contact providers
or perform any external send.
"""

from datetime import datetime, timezone
import uuid

from psycopg.rows import dict_row

from db import get_connection, record_event_in_transaction
from provider_directory import list_eligible_providers_for_service_and_area_with_cursor
from provider_response_reliability import (
    ProviderResponseReliabilityConflictError,
    ProviderResponseReliabilityValidationError,
    record_response_opportunity_with_cursor,
)


class RFQDeliveryValidationError(ValueError):
    """RFQ delivery input is invalid before persistence."""


class RFQDeliveryNotFoundError(LookupError):
    """RFQ or provider handoff does not exist."""


class RFQDeliveryStateError(RuntimeError):
    """RFQ provider handoff is not in the required state."""


class RFQDeliveryEligibilityError(RuntimeError):
    """Provider is not currently eligible for the RFQ service/area."""


class RFQDeliveryConflictError(RuntimeError):
    """Delivery activation conflicts with existing immutable evidence."""


def _validate_uuid(value, field_name: str):
    if not isinstance(value, uuid.UUID):
        raise RFQDeliveryValidationError(f"{field_name} must be a UUID")
    return value


def _normalize_actor(actor: str) -> str:
    if not isinstance(actor, str):
        raise RFQDeliveryValidationError("actor must be text")
    normalized = actor.strip()
    if not normalized:
        raise RFQDeliveryValidationError("actor is required")
    if len(normalized) > 200:
        raise RFQDeliveryValidationError("actor is too long")
    if not normalized.startswith("operator:"):
        raise RFQDeliveryValidationError(
            "RFQ delivery authority must be an operator"
        )
    return normalized


def _validate_deadline(value) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RFQDeliveryValidationError(
            "response_deadline_at must be a timezone-aware datetime"
        )
    return value


def _handoff_result(row):
    return {
        "handoff_id": str(row["id"]),
        "rfq_id": str(row["rfq_id"]),
        "provider_id": str(row["provider_id"]),
        "status": row["status"],
        "authorized_at": row["authorized_at"],
        "authorized_by": row["authorized_by"],
        "delivered_at": row["delivered_at"],
        "response_deadline_at": row["response_deadline_at"],
        "response_reliability_started": row["status"] == "delivered",
    }


def _load_locked_handoff(cursor, request_id, handoff_id):
    cursor.execute(
        """
        SELECT
            h.id,
            h.rfq_id,
            h.provider_id,
            h.status,
            h.authorized_at,
            h.authorized_by,
            h.delivered_at,
            h.response_deadline_at,
            r.request_id,
            r.service_slug,
            r.area_key
        FROM rfq_provider_handoffs h
        INNER JOIN rfqs r ON r.id = h.rfq_id
        WHERE r.request_id = %s
          AND h.id = %s
        FOR UPDATE OF h, r
        """,
        (request_id, handoff_id),
    )
    return cursor.fetchone()


def authorize_rfq_delivery(request_id, handoff_id, *, actor: str):
    """Authorize one provider handoff after current eligibility revalidation.

    This is a pre-send software gate. It performs no provider contact and does not
    create a response opportunity.
    """

    request_id = _validate_uuid(request_id, "request_id")
    handoff_id = _validate_uuid(handoff_id, "handoff_id")
    actor = _normalize_actor(actor)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            handoff = _load_locked_handoff(cur, request_id, handoff_id)
            if handoff is None:
                raise RFQDeliveryNotFoundError("RFQ provider handoff not found")

            if handoff["status"] == "delivered":
                return _handoff_result(handoff)
            if handoff["status"] == "authorized":
                return _handoff_result(handoff)
            if handoff["status"] != "prepared":
                raise RFQDeliveryStateError(
                    f"RFQ handoff cannot be authorized from status {handoff['status']}"
                )

            eligible = list_eligible_providers_for_service_and_area_with_cursor(
                cur,
                handoff["service_slug"],
                handoff["area_key"],
                lock_rows=True,
            )
            eligible_ids = {provider["id"] for provider in eligible}
            if handoff["provider_id"] not in eligible_ids:
                raise RFQDeliveryEligibilityError(
                    "Provider is no longer eligible for RFQ delivery"
                )

            cur.execute(
                """
                UPDATE rfq_provider_handoffs
                SET status = 'authorized',
                    authorized_at = NOW(),
                    authorized_by = %s
                WHERE id = %s
                RETURNING id, rfq_id, provider_id, status,
                          authorized_at, authorized_by,
                          delivered_at, response_deadline_at
                """,
                (actor, handoff_id),
            )
            updated = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="rfq_delivery_authorized",
                actor=actor,
                details={
                    "rfq_id": str(handoff["rfq_id"]),
                    "handoff_id": str(handoff_id),
                    "provider_id": str(handoff["provider_id"]),
                    "service_slug": handoff["service_slug"],
                    "area_key": handoff["area_key"],
                    "provider_contacted": False,
                    "response_reliability_started": False,
                },
            )
            return _handoff_result(updated)


def confirm_rfq_delivery(
    request_id,
    handoff_id,
    response_deadline_at: datetime,
    *,
    actor: str,
):
    """Record confirmed external delivery and start response reliability timing.

    The external send itself is out of scope. This function records the delivery
    confirmation supplied after that external action and atomically creates the
    provider response opportunity using the durable handoff ID.
    """

    request_id = _validate_uuid(request_id, "request_id")
    handoff_id = _validate_uuid(handoff_id, "handoff_id")
    actor = _normalize_actor(actor)
    response_deadline_at = _validate_deadline(response_deadline_at)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            handoff = _load_locked_handoff(cur, request_id, handoff_id)
            if handoff is None:
                raise RFQDeliveryNotFoundError("RFQ provider handoff not found")

            if handoff["status"] == "delivered":
                if handoff["response_deadline_at"] == response_deadline_at:
                    return _handoff_result(handoff)
                raise RFQDeliveryConflictError(
                    "RFQ delivery already confirmed with a different deadline"
                )

            if handoff["status"] != "authorized":
                raise RFQDeliveryStateError(
                    "RFQ handoff must be authorized before delivery confirmation"
                )

            delivered_at = datetime.now(timezone.utc)
            if response_deadline_at <= delivered_at:
                raise RFQDeliveryValidationError(
                    "response_deadline_at must be after delivery confirmation time"
                )

            eligible = list_eligible_providers_for_service_and_area_with_cursor(
                cur,
                handoff["service_slug"],
                handoff["area_key"],
                lock_rows=True,
            )
            eligible_ids = {provider["id"] for provider in eligible}
            if handoff["provider_id"] not in eligible_ids:
                raise RFQDeliveryEligibilityError(
                    "Provider is no longer eligible at delivery confirmation"
                )

            cur.execute(
                """
                UPDATE rfq_provider_handoffs
                SET status = 'delivered',
                    delivered_at = %s,
                    response_deadline_at = %s
                WHERE id = %s
                RETURNING id, rfq_id, provider_id, status,
                          authorized_at, authorized_by,
                          delivered_at, response_deadline_at
                """,
                (delivered_at, response_deadline_at, handoff_id),
            )
            updated = cur.fetchone()

            try:
                record_response_opportunity_with_cursor(
                    cur,
                    handoff["provider_id"],
                    handoff_id,
                    delivered_at,
                    response_deadline_at,
                )
            except (
                ProviderResponseReliabilityValidationError,
                ProviderResponseReliabilityConflictError,
            ) as exc:
                raise RFQDeliveryConflictError(str(exc)) from exc

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="rfq_delivery_confirmed",
                actor=actor,
                details={
                    "rfq_id": str(handoff["rfq_id"]),
                    "handoff_id": str(handoff_id),
                    "provider_id": str(handoff["provider_id"]),
                    "response_deadline_at": response_deadline_at.isoformat(),
                    "response_reliability_started": True,
                },
            )
            return _handoff_result(updated)
