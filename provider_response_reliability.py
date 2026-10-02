"""Deterministic historical provider-response reliability evidence.

The metric measures whether providers respond to an offered opportunity before its
deadline. A timely quote or timely decline both count as reliable responses.

This module does not rank or select providers.
"""

from datetime import datetime, timedelta, timezone
import uuid

from psycopg.rows import dict_row

from db import get_connection


RESPONSE_KINDS = frozenset({"quote", "decline"})
RELIABILITY_WINDOW_DAYS = 90
MIN_COMPLETED_OPPORTUNITIES = 5
RELIABILITY_SCALE_BPS = 10_000


class ProviderResponseReliabilityValidationError(ValueError):
    """Response-reliability input is invalid before persistence."""


class ProviderResponseReliabilityConflictError(RuntimeError):
    """A response observation conflicts with already persisted evidence."""


def _validate_timestamp(value, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ProviderResponseReliabilityValidationError(
            f"{field_name} must be a timezone-aware datetime"
        )
    return value


def _validate_uuid(value, field_name: str):
    if not isinstance(value, uuid.UUID):
        raise ProviderResponseReliabilityValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def record_response_opportunity(
    provider_id,
    opportunity_id,
    offered_at: datetime,
    response_deadline_at: datetime,
):
    """Persist one provider response opportunity idempotently.

    opportunity_id is an opaque deterministic application identifier. A later RFQ
    slice can bind it to the provider-specific RFQ invitation identity.
    """

    _validate_uuid(provider_id, "provider_id")
    _validate_uuid(opportunity_id, "opportunity_id")
    offered_at = _validate_timestamp(offered_at, "offered_at")
    response_deadline_at = _validate_timestamp(
        response_deadline_at,
        "response_deadline_at",
    )
    if response_deadline_at <= offered_at:
        raise ProviderResponseReliabilityValidationError(
            "response_deadline_at must be after offered_at"
        )

    observation_id = uuid.uuid4()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO provider_response_opportunities (
                    id,
                    provider_id,
                    opportunity_id,
                    offered_at,
                    response_deadline_at
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (provider_id, opportunity_id) DO NOTHING
                RETURNING id, provider_id, opportunity_id, offered_at,
                          response_deadline_at, created_at
                """,
                (
                    observation_id,
                    provider_id,
                    opportunity_id,
                    offered_at,
                    response_deadline_at,
                ),
            )
            created = cur.fetchone()
            if created is not None:
                return created

            cur.execute(
                """
                SELECT id, provider_id, opportunity_id, offered_at,
                       response_deadline_at, created_at
                FROM provider_response_opportunities
                WHERE provider_id = %s AND opportunity_id = %s
                """,
                (provider_id, opportunity_id),
            )
            existing = cur.fetchone()

    if (
        existing["offered_at"] != offered_at
        or existing["response_deadline_at"] != response_deadline_at
    ):
        raise ProviderResponseReliabilityConflictError(
            "Response opportunity already exists with different timing"
        )

    return existing


def record_provider_response(
    provider_id,
    opportunity_id,
    response_kind: str,
    responded_at: datetime,
):
    """Persist a quote/decline response idempotently.

    A decline counts as a response because this metric measures responsiveness, not
    willingness to quote.
    """

    _validate_uuid(provider_id, "provider_id")
    _validate_uuid(opportunity_id, "opportunity_id")
    responded_at = _validate_timestamp(responded_at, "responded_at")
    if response_kind not in RESPONSE_KINDS:
        raise ProviderResponseReliabilityValidationError(
            f"Unsupported provider response kind: {response_kind}"
        )

    response_id = uuid.uuid4()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT offered_at
                FROM provider_response_opportunities
                WHERE provider_id = %s AND opportunity_id = %s
                """,
                (provider_id, opportunity_id),
            )
            opportunity = cur.fetchone()
            if opportunity is None:
                raise ProviderResponseReliabilityConflictError(
                    "Response opportunity does not exist"
                )
            if responded_at < opportunity["offered_at"]:
                raise ProviderResponseReliabilityValidationError(
                    "responded_at cannot be before offered_at"
                )

            cur.execute(
                """
                INSERT INTO provider_response_events (
                    id,
                    provider_id,
                    opportunity_id,
                    response_kind,
                    responded_at
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (provider_id, opportunity_id) DO NOTHING
                RETURNING id, provider_id, opportunity_id, response_kind,
                          responded_at, created_at
                """,
                (
                    response_id,
                    provider_id,
                    opportunity_id,
                    response_kind,
                    responded_at,
                ),
            )
            created = cur.fetchone()
            if created is not None:
                return created

            cur.execute(
                """
                SELECT id, provider_id, opportunity_id, response_kind,
                       responded_at, created_at
                FROM provider_response_events
                WHERE provider_id = %s AND opportunity_id = %s
                """,
                (provider_id, opportunity_id),
            )
            existing = cur.fetchone()

    if (
        existing["response_kind"] != response_kind
        or existing["responded_at"] != responded_at
    ):
        raise ProviderResponseReliabilityConflictError(
            "Provider response already exists with different evidence"
        )

    return existing


def calculate_provider_response_reliability(provider_id, as_of=None):
    """Calculate a deterministic 90-day on-time response metric.

    Only completed opportunities count. An opportunity is completed once a response
    exists or the response deadline has passed. Providers with fewer than five
    completed opportunities return insufficient_history and no reliability score.
    """

    _validate_uuid(provider_id, "provider_id")
    as_of = as_of or datetime.now(timezone.utc)
    as_of = _validate_timestamp(as_of, "as_of")
    window_start = as_of - timedelta(days=RELIABILITY_WINDOW_DAYS)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*)::int AS completed_opportunities,
                    COUNT(*) FILTER (
                        WHERE e.responded_at IS NOT NULL
                          AND e.responded_at <= o.response_deadline_at
                    )::int AS on_time_responses,
                    COUNT(*) FILTER (
                        WHERE e.responded_at IS NOT NULL
                          AND e.responded_at > o.response_deadline_at
                    )::int AS late_responses,
                    COUNT(*) FILTER (
                        WHERE e.responded_at IS NULL
                          AND o.response_deadline_at <= %s
                    )::int AS no_responses
                FROM provider_response_opportunities o
                LEFT JOIN provider_response_events e
                  ON e.provider_id = o.provider_id
                 AND e.opportunity_id = o.opportunity_id
                 AND e.responded_at <= %s
                WHERE o.provider_id = %s
                  AND o.offered_at >= %s
                  AND o.offered_at <= %s
                  AND (
                      e.responded_at IS NOT NULL
                      OR o.response_deadline_at <= %s
                  )
                """,
                (
                    as_of,
                    as_of,
                    provider_id,
                    window_start,
                    as_of,
                    as_of,
                ),
            )
            counts = cur.fetchone()

    completed = counts["completed_opportunities"]
    on_time = counts["on_time_responses"]

    if completed < MIN_COMPLETED_OPPORTUNITIES:
        status = "insufficient_history"
        reliability_bps = None
    else:
        status = "sufficient_history"
        reliability_bps = (on_time * RELIABILITY_SCALE_BPS) // completed

    return {
        "provider_id": str(provider_id),
        "factor": "response_reliability",
        "status": status,
        "window_days": RELIABILITY_WINDOW_DAYS,
        "minimum_completed_opportunities": MIN_COMPLETED_OPPORTUNITIES,
        "completed_opportunities": completed,
        "on_time_responses": on_time,
        "late_responses": counts["late_responses"],
        "no_responses": counts["no_responses"],
        "reliability_bps": reliability_bps,
    }
