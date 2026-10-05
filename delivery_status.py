"""Internal service-delivery execution status.

Creates delivery execution state from a confirmed appointment and permits the
human-controlled transition from scheduled to in_progress. Completion and
exceptions are intentionally outside this slice.
"""

import uuid

from psycopg.rows import dict_row

from db import get_connection, record_event_in_transaction


class DeliveryStatusValidationError(ValueError):
    pass


class DeliveryStatusNotFoundError(LookupError):
    pass


class DeliveryStatusStateError(RuntimeError):
    pass


class DeliveryStatusConflictError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise DeliveryStatusValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise DeliveryStatusValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise DeliveryStatusValidationError("actor is required")
    if len(actor) > 200:
        raise DeliveryStatusValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise DeliveryStatusValidationError(
            "Delivery status authority must be an operator"
        )
    return actor


def _normalize_reason(reason, field_name):
    if not isinstance(reason, str):
        raise DeliveryStatusValidationError(
            f"{field_name} must be text"
        )
    reason = reason.strip()
    if not reason:
        raise DeliveryStatusValidationError(
            f"{field_name} is required"
        )
    if len(reason) > 2000:
        raise DeliveryStatusValidationError(
            f"{field_name} is too long"
        )
    return reason


def _result(row):
    return {
        "delivery_status_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "delivery_handoff_id": str(row["delivery_handoff_id"]),
        "appointment_id": str(row["appointment_id"]),
        "provider_id": str(row["provider_id"]),
        "status": row["status"],
        "scheduled_by": row["scheduled_by"],
        "scheduled_reason": row["scheduled_reason"],
        "scheduled_at": row["scheduled_at"],
        "started_by": row["started_by"],
        "start_reason": row["start_reason"],
        "started_at": row["started_at"],
        "updated_at": row["updated_at"],
        "completion_recorded": False,
        "exception_recorded": False,
        "notification_sent": False,
    }


def get_delivery_status(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_delivery_status
                WHERE request_id = %s
                """,
                (request_id,),
            )
            row = cur.fetchone()
            return None if row is None else _result(row)


def initialize_delivery_status(request_id, appointment_id, *, reason, actor):
    request_id = _validate_uuid(request_id, "request_id")
    appointment_id = _validate_uuid(appointment_id, "appointment_id")
    actor = _normalize_actor(actor)
    reason = _normalize_reason(reason, "scheduled_reason")

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
                raise DeliveryStatusNotFoundError("Request not found")
            if request["status"] != "actioned":
                raise DeliveryStatusStateError(
                    "Delivery status requires request status actioned"
                )

            cur.execute(
                """
                SELECT
                    a.id AS appointment_id,
                    a.status AS appointment_status,
                    a.delivery_handoff_id,
                    a.provider_id
                FROM service_delivery_appointments a
                WHERE a.request_id = %s
                  AND a.id = %s
                FOR UPDATE
                """,
                (request_id, appointment_id),
            )
            appointment = cur.fetchone()
            if appointment is None:
                raise DeliveryStatusNotFoundError(
                    "Delivery appointment not found for request"
                )
            if appointment["appointment_status"] != "confirmed":
                raise DeliveryStatusStateError(
                    "Delivery status requires a confirmed appointment"
                )

            cur.execute(
                """
                SELECT *
                FROM service_delivery_status
                WHERE request_id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                if (
                    existing["appointment_id"] == appointment_id
                    and existing["scheduled_by"] == actor
                    and existing["scheduled_reason"] == reason
                ):
                    return _result(existing)
                raise DeliveryStatusConflictError(
                    "A different delivery status record already exists"
                )

            status_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO service_delivery_status (
                    id,
                    request_id,
                    delivery_handoff_id,
                    appointment_id,
                    provider_id,
                    scheduled_by,
                    scheduled_reason
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    status_id,
                    request_id,
                    appointment["delivery_handoff_id"],
                    appointment_id,
                    appointment["provider_id"],
                    actor,
                    reason,
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="delivery_status_scheduled",
                actor=actor,
                details={
                    "delivery_status_id": str(status_id),
                    "appointment_id": str(appointment_id),
                    "provider_id": str(appointment["provider_id"]),
                    "status": "scheduled",
                    "completion_recorded": False,
                    "exception_recorded": False,
                    "notification_sent": False,
                },
            )

            return _result(created)


def start_delivery(request_id, delivery_status_id, *, reason, actor):
    request_id = _validate_uuid(request_id, "request_id")
    delivery_status_id = _validate_uuid(
        delivery_status_id,
        "delivery_status_id",
    )
    actor = _normalize_actor(actor)
    reason = _normalize_reason(reason, "start_reason")

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
                raise DeliveryStatusNotFoundError("Request not found")
            if request["status"] != "actioned":
                raise DeliveryStatusStateError(
                    "Starting delivery requires request status actioned"
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
            current = cur.fetchone()
            if current is None:
                raise DeliveryStatusNotFoundError(
                    "Delivery status record not found for request"
                )

            if current["status"] == "in_progress":
                if (
                    current["started_by"] == actor
                    and current["start_reason"] == reason
                ):
                    return _result(current)
                raise DeliveryStatusConflictError(
                    "Delivery is already in progress with different evidence"
                )

            if current["status"] != "scheduled":
                raise DeliveryStatusStateError(
                    "Delivery must be scheduled before it can start"
                )

            cur.execute(
                """
                UPDATE service_delivery_status
                SET status = 'in_progress',
                    started_by = %s,
                    start_reason = %s,
                    started_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (actor, reason, delivery_status_id),
            )
            started = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="delivery_status_in_progress",
                actor=actor,
                details={
                    "delivery_status_id": str(delivery_status_id),
                    "appointment_id": str(started["appointment_id"]),
                    "provider_id": str(started["provider_id"]),
                    "previous_status": "scheduled",
                    "new_status": "in_progress",
                    "completion_recorded": False,
                    "exception_recorded": False,
                    "notification_sent": False,
                },
            )

            return _result(started)
