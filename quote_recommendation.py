"""Human-authored quote recommendation record.

A recommendation is an immutable operator decision grounded in the current
deterministic comparison set. It is not an award and performs no external action.
"""

import uuid

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from db import get_connection, record_event_in_transaction
from quote_comparison import compare_request_quotes


MAX_RATIONALE_LENGTH = 2000


class QuoteRecommendationValidationError(ValueError):
    """Recommendation input is invalid."""


class QuoteRecommendationNotFoundError(LookupError):
    """Request or normalized quote does not exist."""


class QuoteRecommendationEligibilityError(RuntimeError):
    """The recommended quote is not in the current comparison-ready set."""


class QuoteRecommendationConflictError(RuntimeError):
    """A different immutable recommendation already exists."""


def _validate_uuid(value, field_name: str):
    if not isinstance(value, uuid.UUID):
        raise QuoteRecommendationValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor: str) -> str:
    if not isinstance(actor, str):
        raise QuoteRecommendationValidationError("actor must be text")
    normalized = actor.strip()
    if not normalized:
        raise QuoteRecommendationValidationError("actor is required")
    if len(normalized) > 200:
        raise QuoteRecommendationValidationError("actor is too long")
    if not normalized.startswith("operator:"):
        raise QuoteRecommendationValidationError(
            "Quote recommendation authority must be an operator"
        )
    return normalized


def _normalize_rationale(rationale: str) -> str:
    if not isinstance(rationale, str):
        raise QuoteRecommendationValidationError(
            "rationale must be text"
        )
    normalized = rationale.strip()
    if not normalized:
        raise QuoteRecommendationValidationError(
            "rationale is required"
        )
    if len(normalized) > MAX_RATIONALE_LENGTH:
        raise QuoteRecommendationValidationError(
            f"rationale must be at most {MAX_RATIONALE_LENGTH} characters"
        )
    return normalized


def _result(row):
    return {
        "recommendation_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "normalized_quote_id": str(row["normalized_quote_id"]),
        "recommended_by": row["recommended_by"],
        "rationale": row["rationale"],
        "comparison_snapshot": dict(row["comparison_snapshot"]),
        "created_at": row["created_at"],
        "recommendation_authority": "human",
        "award_created": False,
        "provider_contacted": False,
    }


def get_quote_recommendation(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM quote_recommendations
                WHERE request_id = %s
                """,
                (request_id,),
            )
            row = cur.fetchone()
            return None if row is None else _result(row)


def recommend_quote_for_request(
    request_id,
    normalized_quote_id,
    *,
    rationale: str,
    actor: str,
):
    request_id = _validate_uuid(request_id, "request_id")
    normalized_quote_id = _validate_uuid(
        normalized_quote_id,
        "normalized_quote_id",
    )
    rationale = _normalize_rationale(rationale)
    actor = _normalize_actor(actor)

    comparison = compare_request_quotes(request_id)
    ready_quote_ids = {
        uuid.UUID(item["normalized_quote_id"])
        for item in comparison["quotes"]
    }
    if normalized_quote_id not in ready_quote_ids:
        raise QuoteRecommendationEligibilityError(
            "Recommended quote must belong to the current comparison-ready set"
        )

    snapshot = {
        "quote_count": comparison["quote_count"],
        "price_comparable": comparison["price_comparable"],
        "lowest_price_quote_ids": comparison["lowest_price_quote_ids"],
        "availability_comparable": comparison["availability_comparable"],
        "earliest_available_quote_ids": (
            comparison["earliest_available_quote_ids"]
        ),
        "duration_comparable": comparison["duration_comparable"],
        "shortest_duration_quote_ids": (
            comparison["shortest_duration_quote_ids"]
        ),
        "comparison_gaps": comparison["comparison_gaps"],
    }

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id
                FROM agent_requests
                WHERE id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            if cur.fetchone() is None:
                raise QuoteRecommendationNotFoundError("Request not found")

            cur.execute(
                """
                SELECT *
                FROM quote_recommendations
                WHERE request_id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            existing = cur.fetchone()

            if existing is not None:
                result = _result(existing)
                same = (
                    existing["normalized_quote_id"] == normalized_quote_id
                    and existing["recommended_by"] == actor
                    and existing["rationale"] == rationale
                    and dict(existing["comparison_snapshot"]) == snapshot
                )
                if same:
                    return result
                raise QuoteRecommendationConflictError(
                    "A different quote recommendation already exists"
                )

            cur.execute(
                """
                SELECT id
                FROM normalized_provider_quotes
                WHERE id = %s
                  AND request_id = %s
                """,
                (normalized_quote_id, request_id),
            )
            if cur.fetchone() is None:
                raise QuoteRecommendationNotFoundError(
                    "Normalized quote not found for request"
                )

            recommendation_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO quote_recommendations (
                    id,
                    request_id,
                    normalized_quote_id,
                    recommended_by,
                    rationale,
                    comparison_snapshot
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    recommendation_id,
                    request_id,
                    normalized_quote_id,
                    actor,
                    rationale,
                    Jsonb(snapshot),
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="quote_recommendation_recorded",
                actor=actor,
                details={
                    "recommendation_id": str(recommendation_id),
                    "normalized_quote_id": str(normalized_quote_id),
                    "rationale_present": True,
                    "award_created": False,
                    "provider_contacted": False,
                },
            )
            return _result(created)
