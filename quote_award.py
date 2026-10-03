"""Human-authorized quote award record.

An award is an immutable commercial decision tied to the existing human
recommendation. It performs no provider contact, dispatch, or external action.
"""

import uuid

from psycopg.rows import dict_row

from db import get_connection, record_event_in_transaction
from provider_directory import (
    list_eligible_providers_for_service_and_area_with_cursor,
)
from quote_completeness import assess_quote_completeness


MAX_REASON_LENGTH = 2000


class QuoteAwardValidationError(ValueError):
    """Award input is invalid."""


class QuoteAwardNotFoundError(LookupError):
    """Required request, recommendation, or quote does not exist."""


class QuoteAwardEligibilityError(RuntimeError):
    """The recommended quote/provider is no longer award-eligible."""


class QuoteAwardConflictError(RuntimeError):
    """A different immutable award already exists."""


def _validate_uuid(value, field_name: str):
    if not isinstance(value, uuid.UUID):
        raise QuoteAwardValidationError(f"{field_name} must be a UUID")
    return value


def _normalize_actor(actor: str) -> str:
    if not isinstance(actor, str):
        raise QuoteAwardValidationError("actor must be text")
    normalized = actor.strip()
    if not normalized:
        raise QuoteAwardValidationError("actor is required")
    if len(normalized) > 200:
        raise QuoteAwardValidationError("actor is too long")
    if not normalized.startswith("operator:"):
        raise QuoteAwardValidationError(
            "Quote award authority must be an operator"
        )
    return normalized


def _normalize_reason(reason: str) -> str:
    if not isinstance(reason, str):
        raise QuoteAwardValidationError("reason must be text")
    normalized = reason.strip()
    if not normalized:
        raise QuoteAwardValidationError("reason is required")
    if len(normalized) > MAX_REASON_LENGTH:
        raise QuoteAwardValidationError(
            f"reason must be at most {MAX_REASON_LENGTH} characters"
        )
    return normalized


def _result(row):
    return {
        "award_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "recommendation_id": str(row["recommendation_id"]),
        "normalized_quote_id": str(row["normalized_quote_id"]),
        "provider_id": str(row["provider_id"]),
        "awarded_by": row["awarded_by"],
        "reason": row["reason"],
        "created_at": row["created_at"],
        "award_authority": "human",
        "provider_contacted": False,
        "dispatch_created": False,
        "request_status_changed": False,
    }


def get_quote_award(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM quote_awards
                WHERE request_id = %s
                """,
                (request_id,),
            )
            row = cur.fetchone()
            return None if row is None else _result(row)


def award_recommended_quote(
    request_id,
    recommendation_id,
    *,
    reason: str,
    actor: str,
):
    """Record one immutable human award for the current recommendation."""

    request_id = _validate_uuid(request_id, "request_id")
    recommendation_id = _validate_uuid(
        recommendation_id,
        "recommendation_id",
    )
    reason = _normalize_reason(reason)
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
                raise QuoteAwardNotFoundError("Request not found")

            cur.execute(
                """
                SELECT
                    qr.id AS recommendation_id,
                    qr.normalized_quote_id,
                    nq.handoff_id,
                    nq.provider_id,
                    r.service_slug,
                    r.area_key
                FROM quote_recommendations qr
                INNER JOIN normalized_provider_quotes nq
                    ON nq.id = qr.normalized_quote_id
                INNER JOIN rfq_provider_handoffs h
                    ON h.id = nq.handoff_id
                INNER JOIN rfqs r
                    ON r.id = h.rfq_id
                WHERE qr.request_id = %s
                  AND qr.id = %s
                FOR UPDATE OF qr, nq, h, r
                """,
                (request_id, recommendation_id),
            )
            recommendation = cur.fetchone()
            if recommendation is None:
                raise QuoteAwardNotFoundError(
                    "Quote recommendation not found for request"
                )

            cur.execute(
                """
                SELECT *
                FROM quote_awards
                WHERE request_id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                result = _result(existing)
                same = (
                    existing["recommendation_id"] == recommendation_id
                    and existing["normalized_quote_id"]
                        == recommendation["normalized_quote_id"]
                    and existing["provider_id"]
                        == recommendation["provider_id"]
                    and existing["awarded_by"] == actor
                    and existing["reason"] == reason
                )
                if same:
                    return result
                raise QuoteAwardConflictError(
                    "A different quote award already exists"
                )

            completeness = assess_quote_completeness(
                request_id,
                recommendation["handoff_id"],
            )
            if not completeness["comparison_ready"]:
                raise QuoteAwardEligibilityError(
                    "Recommended quote is no longer comparison-ready"
                )

            eligible = list_eligible_providers_for_service_and_area_with_cursor(
                cur,
                recommendation["service_slug"],
                recommendation["area_key"],
                lock_rows=True,
            )
            eligible_ids = {row["id"] for row in eligible}
            if recommendation["provider_id"] not in eligible_ids:
                raise QuoteAwardEligibilityError(
                    "Recommended provider is no longer currently eligible"
                )

            award_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO quote_awards (
                    id,
                    request_id,
                    recommendation_id,
                    normalized_quote_id,
                    provider_id,
                    awarded_by,
                    reason
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    award_id,
                    request_id,
                    recommendation_id,
                    recommendation["normalized_quote_id"],
                    recommendation["provider_id"],
                    actor,
                    reason,
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="quote_award_recorded",
                actor=actor,
                details={
                    "award_id": str(award_id),
                    "recommendation_id": str(recommendation_id),
                    "normalized_quote_id": str(
                        recommendation["normalized_quote_id"]
                    ),
                    "provider_id": str(recommendation["provider_id"]),
                    "provider_contacted": False,
                    "dispatch_created": False,
                    "request_status_changed": False,
                    "award_authority": "human",
                },
            )

            return _result(created)
