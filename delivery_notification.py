"""Durable preparation of post-award customer/provider notifications.

This module creates deterministic notification content from the immutable
service-delivery handoff. It does not resolve destinations or send anything.
"""

import uuid

from psycopg.rows import dict_row

from db import get_connection, record_event_in_transaction


class DeliveryNotificationValidationError(ValueError):
    pass


class DeliveryNotificationNotFoundError(LookupError):
    pass


class DeliveryNotificationStateError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise DeliveryNotificationValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise DeliveryNotificationValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise DeliveryNotificationValidationError("actor is required")
    if len(actor) > 200:
        raise DeliveryNotificationValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise DeliveryNotificationValidationError(
            "Notification preparation authority must be an operator"
        )
    return actor


def _format_amount(amount_minor, currency):
    return f"{currency.strip()} {amount_minor / 100:.2f}"


def _row_result(row):
    return {
        "notification_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "delivery_handoff_id": str(row["delivery_handoff_id"]),
        "audience_type": row["audience_type"],
        "provider_id": (
            None if row["provider_id"] is None else str(row["provider_id"])
        ),
        "purpose": row["purpose"],
        "subject": row["subject"],
        "body": row["body"],
        "destination_channel": row["destination_channel"],
        "destination_address": row["destination_address"],
        "status": row["status"],
        "prepared_by": row["prepared_by"],
        "created_at": row["created_at"],
        "sent": False,
        "external_action_performed": False,
    }


def get_prepared_delivery_notifications(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_delivery_notifications
                WHERE request_id = %s
                ORDER BY audience_type ASC
                """,
                (request_id,),
            )
            return [_row_result(row) for row in cur.fetchall()]


def prepare_delivery_notifications(request_id, *, actor):
    request_id = _validate_uuid(request_id, "request_id")
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
                raise DeliveryNotificationNotFoundError("Request not found")
            if request["status"] != "actioned":
                raise DeliveryNotificationStateError(
                    "Notification preparation requires request status actioned"
                )

            cur.execute(
                """
                SELECT *
                FROM service_delivery_handoffs
                WHERE request_id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            handoff = cur.fetchone()
            if handoff is None:
                raise DeliveryNotificationNotFoundError(
                    "Delivery handoff not found for request"
                )

            cur.execute(
                """
                SELECT *
                FROM service_delivery_notifications
                WHERE request_id = %s
                ORDER BY audience_type ASC
                FOR UPDATE
                """,
                (request_id,),
            )
            existing = cur.fetchall()
            if existing:
                if len(existing) != 2:
                    raise DeliveryNotificationStateError(
                        "Notification preparation is incomplete"
                    )
                return {
                    "request_id": str(request_id),
                    "delivery_handoff_id": str(handoff["id"]),
                    "notifications": [_row_result(row) for row in existing],
                    "destinations_resolved": False,
                    "sent": False,
                }

            price = _format_amount(
                handoff["amount_minor"],
                handoff["currency"],
            )
            scope = handoff["scope_summary"].strip()

            customer_subject = "Your service request has been awarded"
            customer_body = (
                f"Your service request has been awarded to the selected "
                f"provider. Agreed quote: {price}. Scope: {scope}"
            )

            provider_subject = "Service award ready for coordination"
            provider_body = (
                f"A service request has been awarded to your provider record. "
                f"Agreed quote: {price}. Scope: {scope}"
            )

            rows = []
            for audience_type, provider_id, purpose, subject, body in (
                (
                    "customer",
                    None,
                    "award_confirmation",
                    customer_subject,
                    customer_body,
                ),
                (
                    "provider",
                    handoff["provider_id"],
                    "award_notification",
                    provider_subject,
                    provider_body,
                ),
            ):
                notification_id = uuid.uuid4()
                cur.execute(
                    """
                    INSERT INTO service_delivery_notifications (
                        id,
                        request_id,
                        delivery_handoff_id,
                        audience_type,
                        provider_id,
                        purpose,
                        subject,
                        body,
                        prepared_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        notification_id,
                        request_id,
                        handoff["id"],
                        audience_type,
                        provider_id,
                        purpose,
                        subject,
                        body,
                        actor,
                    ),
                )
                rows.append(cur.fetchone())

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="delivery_notifications_prepared",
                actor=actor,
                details={
                    "delivery_handoff_id": str(handoff["id"]),
                    "notification_ids": [str(row["id"]) for row in rows],
                    "audiences": ["customer", "provider"],
                    "destinations_resolved": False,
                    "sent": False,
                    "external_action_performed": False,
                },
            )

            return {
                "request_id": str(request_id),
                "delivery_handoff_id": str(handoff["id"]),
                "notifications": [_row_result(row) for row in rows],
                "destinations_resolved": False,
                "sent": False,
            }
