"""Preparation-only customer satisfaction follow-up.

Creates one durable post-completion follow-up record. It does not resolve a
destination, send a message, ingest a rating, or change delivery/request state.
"""

import uuid

from psycopg.rows import dict_row

from db import get_connection, record_event_in_transaction


SATISFACTION_QUESTION = (
    "How satisfied are you with the completed service? "
    "Please rate your experience from 1 to 5."
)


class SatisfactionFollowUpValidationError(ValueError):
    pass


class SatisfactionFollowUpNotFoundError(LookupError):
    pass


class SatisfactionFollowUpStateError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise SatisfactionFollowUpValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise SatisfactionFollowUpValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise SatisfactionFollowUpValidationError("actor is required")
    if len(actor) > 200:
        raise SatisfactionFollowUpValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise SatisfactionFollowUpValidationError(
            "Satisfaction follow-up authority must be an operator"
        )
    return actor


def _result(row):
    return {
        "follow_up_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "delivery_status_id": str(row["delivery_status_id"]),
        "provider_id": str(row["provider_id"]),
        "purpose": row["purpose"],
        "question": row["question"],
        "rating_min": row["rating_min"],
        "rating_max": row["rating_max"],
        "destination_channel": row["destination_channel"],
        "destination_address": row["destination_address"],
        "status": row["status"],
        "prepared_by": row["prepared_by"],
        "created_at": row["created_at"],
        "response_recorded": False,
        "sent": False,
        "external_action_performed": False,
    }


def get_satisfaction_follow_up(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_satisfaction_followups
                WHERE request_id = %s
                """,
                (request_id,),
            )
            row = cur.fetchone()
            return None if row is None else _result(row)


def prepare_satisfaction_follow_up(request_id, *, actor):
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
                raise SatisfactionFollowUpNotFoundError("Request not found")
            if request["status"] != "actioned":
                raise SatisfactionFollowUpStateError(
                    "Satisfaction follow-up requires request status actioned"
                )

            cur.execute(
                """
                SELECT id, provider_id, status
                FROM service_delivery_status
                WHERE request_id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            delivery = cur.fetchone()
            if delivery is None:
                raise SatisfactionFollowUpNotFoundError(
                    "Delivery status not found for request"
                )
            if delivery["status"] != "completed":
                raise SatisfactionFollowUpStateError(
                    "Satisfaction follow-up requires completed delivery"
                )

            cur.execute(
                """
                SELECT *
                FROM service_satisfaction_followups
                WHERE request_id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                return _result(existing)

            follow_up_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO service_satisfaction_followups (
                    id,
                    request_id,
                    delivery_status_id,
                    provider_id,
                    question,
                    prepared_by
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    follow_up_id,
                    request_id,
                    delivery["id"],
                    delivery["provider_id"],
                    SATISFACTION_QUESTION,
                    actor,
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="customer_satisfaction_follow_up_prepared",
                actor=actor,
                details={
                    "follow_up_id": str(follow_up_id),
                    "delivery_status_id": str(delivery["id"]),
                    "provider_id": str(delivery["provider_id"]),
                    "rating_min": 1,
                    "rating_max": 5,
                    "destination_resolved": False,
                    "response_recorded": False,
                    "sent": False,
                    "external_action_performed": False,
                },
            )

            return _result(created)
