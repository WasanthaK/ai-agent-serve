"""Internal appointment proposal and confirmation state.

This module records one human-controlled appointment window for an actioned
service-delivery request. It does not send messages or book an external calendar.
"""

from datetime import datetime, timezone
import uuid

from psycopg.rows import dict_row

from db import get_connection, record_event_in_transaction


class DeliveryAppointmentValidationError(ValueError):
    pass


class DeliveryAppointmentNotFoundError(LookupError):
    pass


class DeliveryAppointmentStateError(RuntimeError):
    pass


class DeliveryAppointmentConflictError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise DeliveryAppointmentValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise DeliveryAppointmentValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise DeliveryAppointmentValidationError("actor is required")
    if len(actor) > 200:
        raise DeliveryAppointmentValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise DeliveryAppointmentValidationError(
            "Appointment authority must be an operator"
        )
    return actor


def _normalize_reason(reason, field_name):
    if not isinstance(reason, str):
        raise DeliveryAppointmentValidationError(
            f"{field_name} must be text"
        )
    reason = reason.strip()
    if not reason:
        raise DeliveryAppointmentValidationError(
            f"{field_name} is required"
        )
    if len(reason) > 2000:
        raise DeliveryAppointmentValidationError(
            f"{field_name} is too long"
        )
    return reason


def _validate_window(start_at, end_at):
    for value, field_name in (
        (start_at, "proposed_start_at"),
        (end_at, "proposed_end_at"),
    ):
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise DeliveryAppointmentValidationError(
                f"{field_name} must be a timezone-aware datetime"
            )
    if end_at <= start_at:
        raise DeliveryAppointmentValidationError(
            "proposed_end_at must be after proposed_start_at"
        )
    if start_at <= datetime.now(timezone.utc):
        raise DeliveryAppointmentValidationError(
            "proposed_start_at must be in the future"
        )
    return start_at, end_at


def _result(row):
    return {
        "appointment_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "delivery_handoff_id": str(row["delivery_handoff_id"]),
        "provider_id": str(row["provider_id"]),
        "proposed_start_at": row["proposed_start_at"],
        "proposed_end_at": row["proposed_end_at"],
        "status": row["status"],
        "proposed_by": row["proposed_by"],
        "proposal_reason": row["proposal_reason"],
        "confirmed_by": row["confirmed_by"],
        "confirmation_reason": row["confirmation_reason"],
        "confirmed_at": row["confirmed_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "external_calendar_booking_created": False,
        "notification_sent": False,
    }


def get_delivery_appointment(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_delivery_appointments
                WHERE request_id = %s
                """,
                (request_id,),
            )
            row = cur.fetchone()
            return None if row is None else _result(row)


def propose_delivery_appointment(
    request_id,
    proposed_start_at,
    proposed_end_at,
    *,
    reason,
    actor,
):
    request_id = _validate_uuid(request_id, "request_id")
    actor = _normalize_actor(actor)
    reason = _normalize_reason(reason, "proposal_reason")
    proposed_start_at, proposed_end_at = _validate_window(
        proposed_start_at,
        proposed_end_at,
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
                raise DeliveryAppointmentNotFoundError("Request not found")
            if request["status"] != "actioned":
                raise DeliveryAppointmentStateError(
                    "Appointment proposal requires request status actioned"
                )

            cur.execute(
                """
                SELECT id, provider_id
                FROM service_delivery_handoffs
                WHERE request_id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            handoff = cur.fetchone()
            if handoff is None:
                raise DeliveryAppointmentNotFoundError(
                    "Delivery handoff not found for request"
                )

            cur.execute(
                """
                SELECT *
                FROM service_delivery_appointments
                WHERE request_id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                if (
                    existing["proposed_start_at"] == proposed_start_at
                    and existing["proposed_end_at"] == proposed_end_at
                    and existing["proposed_by"] == actor
                    and existing["proposal_reason"] == reason
                ):
                    return _result(existing)
                raise DeliveryAppointmentConflictError(
                    "A different appointment proposal already exists"
                )

            appointment_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO service_delivery_appointments (
                    id,
                    request_id,
                    delivery_handoff_id,
                    provider_id,
                    proposed_start_at,
                    proposed_end_at,
                    proposed_by,
                    proposal_reason
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    appointment_id,
                    request_id,
                    handoff["id"],
                    handoff["provider_id"],
                    proposed_start_at,
                    proposed_end_at,
                    actor,
                    reason,
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="delivery_appointment_proposed",
                actor=actor,
                details={
                    "appointment_id": str(appointment_id),
                    "delivery_handoff_id": str(handoff["id"]),
                    "provider_id": str(handoff["provider_id"]),
                    "proposed_start_at": proposed_start_at.isoformat(),
                    "proposed_end_at": proposed_end_at.isoformat(),
                    "external_calendar_booking_created": False,
                    "notification_sent": False,
                },
            )

            return _result(created)


def confirm_delivery_appointment(
    request_id,
    appointment_id,
    *,
    reason,
    actor,
):
    request_id = _validate_uuid(request_id, "request_id")
    appointment_id = _validate_uuid(appointment_id, "appointment_id")
    actor = _normalize_actor(actor)
    reason = _normalize_reason(reason, "confirmation_reason")

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
                raise DeliveryAppointmentNotFoundError("Request not found")
            if request["status"] != "actioned":
                raise DeliveryAppointmentStateError(
                    "Appointment confirmation requires request status actioned"
                )

            cur.execute(
                """
                SELECT *
                FROM service_delivery_appointments
                WHERE request_id = %s
                  AND id = %s
                FOR UPDATE
                """,
                (request_id, appointment_id),
            )
            appointment = cur.fetchone()
            if appointment is None:
                raise DeliveryAppointmentNotFoundError(
                    "Appointment proposal not found for request"
                )

            if appointment["status"] == "confirmed":
                if (
                    appointment["confirmed_by"] == actor
                    and appointment["confirmation_reason"] == reason
                ):
                    return _result(appointment)
                raise DeliveryAppointmentConflictError(
                    "Appointment is already confirmed with different evidence"
                )

            if appointment["status"] != "proposed":
                raise DeliveryAppointmentStateError(
                    "Appointment must be proposed before confirmation"
                )

            cur.execute(
                """
                UPDATE service_delivery_appointments
                SET status = 'confirmed',
                    confirmed_by = %s,
                    confirmation_reason = %s,
                    confirmed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (actor, reason, appointment_id),
            )
            confirmed = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="delivery_appointment_confirmed",
                actor=actor,
                details={
                    "appointment_id": str(appointment_id),
                    "proposed_start_at": confirmed[
                        "proposed_start_at"
                    ].isoformat(),
                    "proposed_end_at": confirmed[
                        "proposed_end_at"
                    ].isoformat(),
                    "external_calendar_booking_created": False,
                    "notification_sent": False,
                },
            )

            return _result(confirmed)
