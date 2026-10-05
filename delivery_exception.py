"""Immutable delay and service-issue recording for active delivery.

Exceptions are operator-recorded evidence only. They do not resolve themselves,
change delivery/request status, notify anyone, or create intervention authority.
"""

from datetime import datetime, timezone
import uuid

from psycopg.rows import dict_row

from db import get_connection, record_event_in_transaction


ALLOWED_EXCEPTION_KINDS = frozenset({"delay", "service_issue"})


class DeliveryExceptionValidationError(ValueError):
    pass


class DeliveryExceptionNotFoundError(LookupError):
    pass


class DeliveryExceptionStateError(RuntimeError):
    pass


class DeliveryExceptionConflictError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise DeliveryExceptionValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise DeliveryExceptionValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise DeliveryExceptionValidationError("actor is required")
    if len(actor) > 200:
        raise DeliveryExceptionValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise DeliveryExceptionValidationError(
            "Delivery exception authority must be an operator"
        )
    return actor


def _normalize_summary(summary):
    if not isinstance(summary, str):
        raise DeliveryExceptionValidationError("summary must be text")
    summary = summary.strip()
    if not summary:
        raise DeliveryExceptionValidationError("summary is required")
    if len(summary) > 2000:
        raise DeliveryExceptionValidationError("summary is too long")
    return summary


def _normalize_kind(exception_kind):
    if not isinstance(exception_kind, str):
        raise DeliveryExceptionValidationError(
            "exception_kind must be text"
        )
    exception_kind = exception_kind.strip().lower()
    if exception_kind not in ALLOWED_EXCEPTION_KINDS:
        raise DeliveryExceptionValidationError(
            "exception_kind must be delay or service_issue"
        )
    return exception_kind


def _validate_time(value, field_name):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise DeliveryExceptionValidationError(
            f"{field_name} must be a timezone-aware datetime"
        )
    return value


def _result(row):
    intervention_created = bool(
        row.get("human_intervention_created", False)
    )
    return {
        "exception_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "delivery_status_id": str(row["delivery_status_id"]),
        "provider_id": str(row["provider_id"]),
        "exception_kind": row["exception_kind"],
        "occurred_at": row["occurred_at"],
        "summary": row["summary"],
        "expected_resolution_at": row["expected_resolution_at"],
        "recorded_by": row["recorded_by"],
        "created_at": row["created_at"],
        "resolved": False,
        "human_intervention_created": intervention_created,
        "notification_sent": False,
    }


def get_delivery_exceptions(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    e.*,
                    EXISTS (
                        SELECT 1
                        FROM service_delivery_interventions i
                        WHERE i.exception_id = e.id
                    ) AS human_intervention_created
                FROM service_delivery_exceptions e
                WHERE e.request_id = %s
                ORDER BY e.occurred_at ASC, e.created_at ASC, e.id ASC
                """,
                (request_id,),
            )
            return [_result(row) for row in cur.fetchall()]


def record_delivery_exception(
    request_id,
    delivery_status_id,
    exception_id,
    exception_kind,
    occurred_at,
    *,
    summary,
    expected_resolution_at=None,
    actor,
):
    request_id = _validate_uuid(request_id, "request_id")
    delivery_status_id = _validate_uuid(
        delivery_status_id,
        "delivery_status_id",
    )
    exception_id = _validate_uuid(exception_id, "exception_id")
    exception_kind = _normalize_kind(exception_kind)
    occurred_at = _validate_time(occurred_at, "occurred_at")
    actor = _normalize_actor(actor)
    summary = _normalize_summary(summary)

    if occurred_at > datetime.now(timezone.utc):
        raise DeliveryExceptionValidationError(
            "occurred_at cannot be in the future"
        )

    if expected_resolution_at is not None:
        expected_resolution_at = _validate_time(
            expected_resolution_at,
            "expected_resolution_at",
        )
        if expected_resolution_at <= occurred_at:
            raise DeliveryExceptionValidationError(
                "expected_resolution_at must be after occurred_at"
            )

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
                raise DeliveryExceptionNotFoundError("Request not found")
            if request["status"] != "actioned":
                raise DeliveryExceptionStateError(
                    "Delivery exceptions require request status actioned"
                )

            cur.execute(
                """
                SELECT *
                FROM service_delivery_status
                WHERE request_id = %s
                  AND id = %s
                FOR UPDATE
                """,
                (request_id, delivery_status_id),
            )
            delivery = cur.fetchone()
            if delivery is None:
                raise DeliveryExceptionNotFoundError(
                    "Delivery status record not found for request"
                )
            if delivery["status"] not in {"scheduled", "in_progress"}:
                raise DeliveryExceptionStateError(
                    "Delivery exception requires active delivery"
                )
            if (
                exception_kind == "service_issue"
                and delivery["status"] != "in_progress"
            ):
                raise DeliveryExceptionStateError(
                    "service_issue requires delivery status in_progress"
                )

            cur.execute(
                """
                SELECT
                    e.*,
                    EXISTS (
                        SELECT 1
                        FROM service_delivery_interventions i
                        WHERE i.exception_id = e.id
                    ) AS human_intervention_created
                FROM service_delivery_exceptions e
                WHERE e.id = %s
                FOR UPDATE OF e
                """,
                (exception_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                same = (
                    existing["request_id"] == request_id
                    and existing["delivery_status_id"] == delivery_status_id
                    and existing["provider_id"] == delivery["provider_id"]
                    and existing["exception_kind"] == exception_kind
                    and existing["occurred_at"] == occurred_at
                    and existing["summary"] == summary
                    and existing["expected_resolution_at"]
                    == expected_resolution_at
                    and existing["recorded_by"] == actor
                )
                if same:
                    return _result(existing)
                raise DeliveryExceptionConflictError(
                    "exception_id already exists with different evidence"
                )

            cur.execute(
                """
                INSERT INTO service_delivery_exceptions (
                    id,
                    request_id,
                    delivery_status_id,
                    provider_id,
                    exception_kind,
                    occurred_at,
                    summary,
                    expected_resolution_at,
                    recorded_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    exception_id,
                    request_id,
                    delivery_status_id,
                    delivery["provider_id"],
                    exception_kind,
                    occurred_at,
                    summary,
                    expected_resolution_at,
                    actor,
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="delivery_exception_recorded",
                actor=actor,
                details={
                    "exception_id": str(exception_id),
                    "delivery_status_id": str(delivery_status_id),
                    "provider_id": str(delivery["provider_id"]),
                    "exception_kind": exception_kind,
                    "occurred_at": occurred_at.isoformat(),
                    "expected_resolution_at": (
                        None
                        if expected_resolution_at is None
                        else expected_resolution_at.isoformat()
                    ),
                    "delivery_status": delivery["status"],
                    "resolved": False,
                    "human_intervention_created": False,
                    "notification_sent": False,
                },
            )

            return _result(created)
