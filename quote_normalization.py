"""Deterministic structured quote normalization foundation.

This module stores already-structured commercial quote fields against a governed
provider quote response. It performs no document parsing, model extraction,
comparison, recommendation, provider selection, or external action.
"""

from datetime import date, datetime
import uuid

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from db import get_connection, record_event_in_transaction


MAX_LIST_ITEMS = 50
MAX_LIST_ITEM_LENGTH = 500
MAX_SCOPE_LENGTH = 5000


class QuoteNormalizationValidationError(ValueError):
    """Normalized quote input is invalid before persistence."""


class QuoteNormalizationNotFoundError(LookupError):
    """The governed RFQ quote response does not exist."""


class QuoteNormalizationStateError(RuntimeError):
    """The RFQ response cannot be normalized in its current state."""


class QuoteNormalizationConflictError(RuntimeError):
    """A different immutable normalized quote already exists."""


def _validate_uuid(value, field_name: str):
    if not isinstance(value, uuid.UUID):
        raise QuoteNormalizationValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor: str) -> str:
    if not isinstance(actor, str):
        raise QuoteNormalizationValidationError("actor must be text")
    normalized = actor.strip()
    if not normalized:
        raise QuoteNormalizationValidationError("actor is required")
    if len(normalized) > 200:
        raise QuoteNormalizationValidationError("actor is too long")
    if not normalized.startswith("operator:"):
        raise QuoteNormalizationValidationError(
            "Quote normalization authority must be an operator"
        )
    return normalized


def _normalize_currency(currency: str) -> str:
    if not isinstance(currency, str):
        raise QuoteNormalizationValidationError("currency must be text")
    normalized = currency.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise QuoteNormalizationValidationError(
            "currency must be a three-letter code"
        )
    return normalized


def _normalize_scope(scope_summary: str) -> str:
    if not isinstance(scope_summary, str):
        raise QuoteNormalizationValidationError(
            "scope_summary must be text"
        )
    normalized = scope_summary.strip()
    if not normalized:
        raise QuoteNormalizationValidationError(
            "scope_summary is required"
        )
    if len(normalized) > MAX_SCOPE_LENGTH:
        raise QuoteNormalizationValidationError(
            f"scope_summary must be at most {MAX_SCOPE_LENGTH} characters"
        )
    return normalized


def _normalize_text_list(value, field_name: str):
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise QuoteNormalizationValidationError(
            f"{field_name} must be a list"
        )
    if len(value) > MAX_LIST_ITEMS:
        raise QuoteNormalizationValidationError(
            f"{field_name} may contain at most {MAX_LIST_ITEMS} items"
        )

    normalized = []
    for item in value:
        if not isinstance(item, str):
            raise QuoteNormalizationValidationError(
                f"{field_name} items must be text"
            )
        text = item.strip()
        if not text:
            raise QuoteNormalizationValidationError(
                f"{field_name} items must not be blank"
            )
        if len(text) > MAX_LIST_ITEM_LENGTH:
            raise QuoteNormalizationValidationError(
                f"{field_name} items must be at most "
                f"{MAX_LIST_ITEM_LENGTH} characters"
            )
        normalized.append(text)
    return normalized


def _validate_optional_date(value, field_name: str):
    if value is None:
        return None
    if not isinstance(value, date) or isinstance(value, datetime):
        raise QuoteNormalizationValidationError(
            f"{field_name} must be a date"
        )
    return value


def _validate_optional_timestamp(value, field_name: str):
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise QuoteNormalizationValidationError(
            f"{field_name} must be a timezone-aware datetime"
        )
    return value


def _quote_result(row):
    return {
        "normalized_quote_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "handoff_id": str(row["handoff_id"]),
        "provider_id": str(row["provider_id"]),
        "response_event_id": str(row["response_event_id"]),
        "amount_minor": row["amount_minor"],
        "currency": row["currency"].strip(),
        "scope_summary": row["scope_summary"],
        "exclusions": list(row["exclusions"]),
        "terms": list(row["terms"]),
        "available_from": row["available_from"],
        "estimated_duration_days": row["estimated_duration_days"],
        "validity_expires_at": row["validity_expires_at"],
        "normalized_by": row["normalized_by"],
        "created_at": row["created_at"],
        "evaluated": False,
        "selected": False,
    }


def get_normalized_quote(request_id, handoff_id):
    request_id = _validate_uuid(request_id, "request_id")
    handoff_id = _validate_uuid(handoff_id, "handoff_id")

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT q.*
                FROM normalized_provider_quotes q
                WHERE q.request_id = %s
                  AND q.handoff_id = %s
                """,
                (request_id, handoff_id),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return _quote_result(row)


def normalize_structured_quote(
    request_id,
    handoff_id,
    *,
    amount_minor: int,
    currency: str,
    scope_summary: str,
    exclusions=None,
    terms=None,
    available_from=None,
    estimated_duration_days=None,
    validity_expires_at=None,
    actor: str,
):
    """Persist one immutable structured quote for a governed quote response."""

    request_id = _validate_uuid(request_id, "request_id")
    handoff_id = _validate_uuid(handoff_id, "handoff_id")
    actor = _normalize_actor(actor)

    if not isinstance(amount_minor, int) or isinstance(amount_minor, bool):
        raise QuoteNormalizationValidationError(
            "amount_minor must be an integer"
        )
    if amount_minor < 0:
        raise QuoteNormalizationValidationError(
            "amount_minor must be non-negative"
        )

    currency = _normalize_currency(currency)
    scope_summary = _normalize_scope(scope_summary)
    exclusions = _normalize_text_list(exclusions, "exclusions")
    terms = _normalize_text_list(terms, "terms")
    available_from = _validate_optional_date(
        available_from,
        "available_from",
    )
    validity_expires_at = _validate_optional_timestamp(
        validity_expires_at,
        "validity_expires_at",
    )

    if estimated_duration_days is not None:
        if (
            not isinstance(estimated_duration_days, int)
            or isinstance(estimated_duration_days, bool)
            or estimated_duration_days <= 0
        ):
            raise QuoteNormalizationValidationError(
                "estimated_duration_days must be a positive integer"
            )

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    h.id AS handoff_id,
                    h.provider_id,
                    h.status,
                    r.request_id,
                    e.id AS response_event_id,
                    e.response_kind
                FROM rfq_provider_handoffs h
                INNER JOIN rfqs r ON r.id = h.rfq_id
                LEFT JOIN provider_response_events e
                  ON e.provider_id = h.provider_id
                 AND e.opportunity_id = h.id
                WHERE r.request_id = %s
                  AND h.id = %s
                FOR UPDATE OF h, r
                """,
                (request_id, handoff_id),
            )
            governed = cur.fetchone()

            if governed is None:
                raise QuoteNormalizationNotFoundError(
                    "RFQ provider handoff not found"
                )
            if governed["status"] != "delivered":
                raise QuoteNormalizationStateError(
                    "Quote normalization requires a delivered RFQ handoff"
                )
            if governed["response_event_id"] is None:
                raise QuoteNormalizationStateError(
                    "Provider quote response is required before normalization"
                )
            if governed["response_kind"] != "quote":
                raise QuoteNormalizationStateError(
                    "Only provider quote responses can be normalized"
                )

            cur.execute(
                """
                SELECT *
                FROM normalized_provider_quotes
                WHERE handoff_id = %s
                FOR UPDATE
                """,
                (handoff_id,),
            )
            existing = cur.fetchone()

            desired = {
                "amount_minor": amount_minor,
                "currency": currency,
                "scope_summary": scope_summary,
                "exclusions": exclusions,
                "terms": terms,
                "available_from": available_from,
                "estimated_duration_days": estimated_duration_days,
                "validity_expires_at": validity_expires_at,
                "normalized_by": actor,
            }

            if existing is not None:
                current = _quote_result(existing)
                same = all(
                    current[key] == value
                    for key, value in desired.items()
                )
                if same:
                    return current
                raise QuoteNormalizationConflictError(
                    "A different normalized quote already exists for this handoff"
                )

            quote_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO normalized_provider_quotes (
                    id,
                    request_id,
                    handoff_id,
                    provider_id,
                    response_event_id,
                    amount_minor,
                    currency,
                    scope_summary,
                    exclusions,
                    terms,
                    available_from,
                    estimated_duration_days,
                    validity_expires_at,
                    normalized_by
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                RETURNING *
                """,
                (
                    quote_id,
                    request_id,
                    handoff_id,
                    governed["provider_id"],
                    governed["response_event_id"],
                    amount_minor,
                    currency,
                    scope_summary,
                    Jsonb(exclusions),
                    Jsonb(terms),
                    available_from,
                    estimated_duration_days,
                    validity_expires_at,
                    actor,
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="normalized_quote_recorded",
                actor=actor,
                details={
                    "normalized_quote_id": str(quote_id),
                    "handoff_id": str(handoff_id),
                    "provider_id": str(governed["provider_id"]),
                    "response_event_id": str(governed["response_event_id"]),
                    "currency": currency,
                    "amount_minor": amount_minor,
                    "has_exclusions": bool(exclusions),
                    "has_terms": bool(terms),
                    "has_available_from": available_from is not None,
                    "has_estimated_duration": (
                        estimated_duration_days is not None
                    ),
                    "has_validity_expiry": validity_expires_at is not None,
                    "evaluated": False,
                    "selected": False,
                },
            )

            return _quote_result(created)
