"""Deterministic structured quotation persistence.

This foundation records operator-supplied quotation facts for an already governed
quote response. It does not parse documents, evaluate quotations, rank providers,
select a winner, dispatch work, or contact external systems.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
import uuid

from psycopg.rows import dict_row

from db import get_connection, record_event_in_transaction


_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class StructuredQuotationValidationError(ValueError):
    pass


class StructuredQuotationNotFoundError(LookupError):
    pass


class StructuredQuotationStateError(RuntimeError):
    pass


class StructuredQuotationConflictError(RuntimeError):
    pass


def _text(value, field, *, required=False, max_length=5000):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise StructuredQuotationValidationError(f"{field} must be text")
    value = value.strip()
    if required and not value:
        raise StructuredQuotationValidationError(f"{field} is required")
    if len(value) > max_length:
        raise StructuredQuotationValidationError(f"{field} is too long")
    return value or None


def _actor(value):
    value = _text(value, "actor", required=True, max_length=200)
    if not value.startswith("operator:"):
        raise StructuredQuotationValidationError(
            "Structured quotation authority must be an operator"
        )
    return value


def _amount_minor(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StructuredQuotationValidationError(
            "total_amount_minor must be a non-negative integer"
        )
    return value


def record_structured_quotation(
    request_id,
    handoff_id,
    *,
    currency: str,
    total_amount_minor: int,
    scope_text: str,
    submitted_at: datetime,
    actor: str,
    availability_text=None,
    exclusions_text=None,
    terms_text=None,
):
    if not isinstance(request_id, uuid.UUID) or not isinstance(handoff_id, uuid.UUID):
        raise StructuredQuotationValidationError(
            "request_id and handoff_id must be UUIDs"
        )
    currency = _text(currency, "currency", required=True, max_length=3)
    if not _CURRENCY_RE.fullmatch(currency):
        raise StructuredQuotationValidationError(
            "currency must be an uppercase ISO-style three-letter code"
        )
    total_amount_minor = _amount_minor(total_amount_minor)
    scope_text = _text(scope_text, "scope_text", required=True)
    availability_text = _text(availability_text, "availability_text")
    exclusions_text = _text(exclusions_text, "exclusions_text")
    terms_text = _text(terms_text, "terms_text")
    if not isinstance(submitted_at, datetime) or submitted_at.tzinfo is None:
        raise StructuredQuotationValidationError(
            "submitted_at must be a timezone-aware datetime"
        )
    actor = _actor(actor)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT h.id, h.provider_id, h.status, h.delivered_at,
                       e.response_kind, e.responded_at
                FROM rfq_provider_handoffs h
                INNER JOIN rfqs r ON r.id = h.rfq_id
                LEFT JOIN provider_response_events e
                  ON e.provider_id = h.provider_id
                 AND e.opportunity_id = h.id
                WHERE r.request_id = %s AND h.id = %s
                FOR UPDATE OF h, r
                """,
                (request_id, handoff_id),
            )
            handoff = cur.fetchone()
            if handoff is None:
                raise StructuredQuotationNotFoundError("RFQ provider handoff not found")
            if handoff["status"] != "delivered" or handoff["response_kind"] != "quote":
                raise StructuredQuotationStateError(
                    "Structured quotation requires a recorded quote response"
                )
            if submitted_at < handoff["delivered_at"]:
                raise StructuredQuotationValidationError(
                    "submitted_at cannot be before RFQ delivery"
                )

            quotation_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO provider_quotations (
                    id, handoff_id, provider_id, currency, total_amount_minor,
                    availability_text, scope_text, exclusions_text, terms_text,
                    submitted_at, recorded_by
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (handoff_id) DO NOTHING
                RETURNING *
                """,
                (
                    quotation_id, handoff_id, handoff["provider_id"], currency,
                    total_amount_minor, availability_text, scope_text,
                    exclusions_text, terms_text, submitted_at, actor,
                ),
            )
            quotation = cur.fetchone()
            created = quotation is not None
            if not created:
                cur.execute(
                    "SELECT * FROM provider_quotations WHERE handoff_id = %s",
                    (handoff_id,),
                )
                quotation = cur.fetchone()
                evidence = (
                    currency, total_amount_minor, availability_text, scope_text,
                    exclusions_text, terms_text, submitted_at,
                )
                existing = (
                    quotation["currency"], quotation["total_amount_minor"],
                    quotation["availability_text"], quotation["scope_text"],
                    quotation["exclusions_text"], quotation["terms_text"],
                    quotation["submitted_at"],
                )
                if existing != evidence:
                    raise StructuredQuotationConflictError(
                        "Structured quotation already exists with different evidence"
                    )

            if created:
                record_event_in_transaction(
                    cur,
                    request_id=request_id,
                    event_type="structured_quotation_recorded",
                    actor=actor,
                    details={
                        "quotation_id": str(quotation["id"]),
                        "handoff_id": str(handoff_id),
                        "provider_id": str(handoff["provider_id"]),
                        "currency": currency,
                        "total_amount_minor": total_amount_minor,
                        "evaluation_performed": False,
                        "ranking_performed": False,
                    },
                )

            return {
                "quotation_id": str(quotation["id"]),
                "handoff_id": str(quotation["handoff_id"]),
                "provider_id": str(quotation["provider_id"]),
                "currency": quotation["currency"],
                "total_amount_minor": quotation["total_amount_minor"],
                "availability_text": quotation["availability_text"],
                "scope_text": quotation["scope_text"],
                "exclusions_text": quotation["exclusions_text"],
                "terms_text": quotation["terms_text"],
                "submitted_at": quotation["submitted_at"],
                "created_at": quotation["created_at"],
            }
