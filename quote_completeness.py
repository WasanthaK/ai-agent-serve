"""Deterministic quote completeness assessment.

This module evaluates normalized quote records only. It does not compare quotes,
score providers, recommend a winner, select a provider, or perform model inference.
"""

from datetime import datetime, timezone
from uuid import UUID

from quote_normalization import get_normalized_quote


class QuoteCompletenessNotFoundError(LookupError):
    """The normalized quote does not exist."""


def assess_quote_completeness(
    request_id: UUID,
    handoff_id: UUID,
    *,
    as_of: datetime | None = None,
):
    """Assess whether one normalized quote is ready for comparison."""

    quote = get_normalized_quote(request_id, handoff_id)
    if quote is None:
        raise QuoteCompletenessNotFoundError("Normalized quote not found")

    if as_of is None:
        as_of = datetime.now(timezone.utc)
    if not isinstance(as_of, datetime) or as_of.tzinfo is None:
        raise ValueError("as_of must be a timezone-aware datetime")

    missing_required = []
    informational_gaps = []
    blocking_reasons = []

    if quote["amount_minor"] is None:
        missing_required.append("amount_minor")
    if not quote["currency"]:
        missing_required.append("currency")
    if not quote["scope_summary"].strip():
        missing_required.append("scope_summary")

    if not quote["exclusions"]:
        missing_required.append("exclusions")
    if not quote["terms"]:
        missing_required.append("terms")

    if quote["available_from"] is None:
        informational_gaps.append("available_from")
    if quote["estimated_duration_days"] is None:
        informational_gaps.append("estimated_duration_days")
    if quote["validity_expires_at"] is None:
        informational_gaps.append("validity_expires_at")
    elif quote["validity_expires_at"] <= as_of:
        blocking_reasons.append("quote_expired")

    if missing_required:
        status = "incomplete"
        comparison_ready = False
        requires_human_review = True
    elif blocking_reasons:
        status = "needs_human_review"
        comparison_ready = False
        requires_human_review = True
    else:
        status = "complete"
        comparison_ready = True
        requires_human_review = bool(informational_gaps)

    return {
        "normalized_quote_id": quote["normalized_quote_id"],
        "request_id": quote["request_id"],
        "handoff_id": quote["handoff_id"],
        "provider_id": quote["provider_id"],
        "status": status,
        "comparison_ready": comparison_ready,
        "requires_human_review": requires_human_review,
        "missing_required_fields": missing_required,
        "informational_gaps": informational_gaps,
        "blocking_reasons": blocking_reasons,
        "evaluated": False,
        "recommended": False,
        "selected": False,
    }
