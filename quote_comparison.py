"""Deterministic factual comparison of normalized provider quotes.

This module compares only persisted, comparison-ready normalized quotes from the
same request. It does not recommend, select, rank providers overall, convert
currencies, or use model inference.
"""

from datetime import datetime, timezone
from uuid import UUID

from psycopg.rows import dict_row

from db import get_connection
from quote_completeness import assess_quote_completeness


class QuoteComparisonNotReadyError(RuntimeError):
    """There are not enough comparison-ready quotes for deterministic comparison."""


def compare_request_quotes(
    request_id: UUID,
    *,
    as_of: datetime | None = None,
):
    if not isinstance(request_id, UUID):
        raise ValueError("request_id must be a UUID")
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    if not isinstance(as_of, datetime) or as_of.tzinfo is None:
        raise ValueError("as_of must be a timezone-aware datetime")

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    id,
                    handoff_id,
                    provider_id,
                    amount_minor,
                    currency,
                    scope_summary,
                    exclusions,
                    terms,
                    available_from,
                    estimated_duration_days,
                    validity_expires_at
                FROM normalized_provider_quotes
                WHERE request_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (request_id,),
            )
            rows = cur.fetchall()

    quotes = []
    excluded = []

    for row in rows:
        completeness = assess_quote_completeness(
            request_id,
            row["handoff_id"],
            as_of=as_of,
        )
        item = {
            "normalized_quote_id": str(row["id"]),
            "handoff_id": str(row["handoff_id"]),
            "provider_id": str(row["provider_id"]),
            "amount_minor": row["amount_minor"],
            "currency": row["currency"].strip(),
            "scope_summary": row["scope_summary"],
            "exclusions": list(row["exclusions"]),
            "terms": list(row["terms"]),
            "available_from": row["available_from"],
            "estimated_duration_days": row["estimated_duration_days"],
            "validity_expires_at": row["validity_expires_at"],
        }
        if completeness["comparison_ready"]:
            quotes.append(item)
        else:
            excluded.append({
                "normalized_quote_id": str(row["id"]),
                "handoff_id": str(row["handoff_id"]),
                "provider_id": str(row["provider_id"]),
                "completeness_status": completeness["status"],
                "missing_required_fields": (
                    completeness["missing_required_fields"]
                ),
                "blocking_reasons": completeness["blocking_reasons"],
            })

    if len(quotes) < 2:
        raise QuoteComparisonNotReadyError(
            "At least two comparison-ready normalized quotes are required"
        )

    currencies = sorted({quote["currency"] for quote in quotes})
    same_currency = len(currencies) == 1

    lowest_price_ids = []
    if same_currency:
        minimum = min(quote["amount_minor"] for quote in quotes)
        lowest_price_ids = [
            quote["normalized_quote_id"]
            for quote in quotes
            if quote["amount_minor"] == minimum
        ]

    availability_comparable = all(
        quote["available_from"] is not None for quote in quotes
    )
    earliest_available_ids = []
    if availability_comparable:
        earliest = min(quote["available_from"] for quote in quotes)
        earliest_available_ids = [
            quote["normalized_quote_id"]
            for quote in quotes
            if quote["available_from"] == earliest
        ]

    duration_comparable = all(
        quote["estimated_duration_days"] is not None
        for quote in quotes
    )
    shortest_duration_ids = []
    if duration_comparable:
        shortest = min(
            quote["estimated_duration_days"] for quote in quotes
        )
        shortest_duration_ids = [
            quote["normalized_quote_id"]
            for quote in quotes
            if quote["estimated_duration_days"] == shortest
        ]

    comparison_gaps = []
    if not same_currency:
        comparison_gaps.append("mixed_currencies")
    if not availability_comparable:
        comparison_gaps.append("availability_not_complete")
    if not duration_comparable:
        comparison_gaps.append("duration_not_complete")

    return {
        "request_id": str(request_id),
        "status": "comparison_available",
        "quote_count": len(quotes),
        "quotes": quotes,
        "excluded_quotes": excluded,
        "price_comparable": same_currency,
        "currencies": currencies,
        "lowest_price_quote_ids": lowest_price_ids,
        "availability_comparable": availability_comparable,
        "earliest_available_quote_ids": earliest_available_ids,
        "duration_comparable": duration_comparable,
        "shortest_duration_quote_ids": shortest_duration_ids,
        "comparison_gaps": comparison_gaps,
        "overall_winner_quote_id": None,
        "recommended_quote_id": None,
        "selected_quote_id": None,
        "requires_human_review": bool(comparison_gaps),
    }
