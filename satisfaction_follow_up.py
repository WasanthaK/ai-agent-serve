"""Customer satisfaction follow-up preparation and response evidence.

Creates one durable post-completion follow-up record and permits one immutable
operator-recorded satisfaction response. It does not resolve a destination,
send a message, trigger a review/complaint, or change delivery/request state.
"""

from datetime import datetime, timezone
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


class SatisfactionFollowUpConflictError(RuntimeError):
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


def _normalize_response_source(response_source):
    if not isinstance(response_source, str):
        raise SatisfactionFollowUpValidationError(
            "response_source must be text"
        )
    response_source = response_source.strip()
    if not response_source:
        raise SatisfactionFollowUpValidationError(
            "response_source is required"
        )
    if len(response_source) > 100:
        raise SatisfactionFollowUpValidationError(
            "response_source is too long"
        )
    return response_source


def _normalize_comment(comment):
    if comment is None:
        return None
    if not isinstance(comment, str):
        raise SatisfactionFollowUpValidationError("comment must be text")
    comment = comment.strip()
    if not comment:
        return None
    if len(comment) > 4000:
        raise SatisfactionFollowUpValidationError("comment is too long")
    return comment


def _validate_responded_at(responded_at):
    if not isinstance(responded_at, datetime) or responded_at.tzinfo is None:
        raise SatisfactionFollowUpValidationError(
            "responded_at must be a timezone-aware datetime"
        )
    if responded_at > datetime.now(timezone.utc):
        raise SatisfactionFollowUpValidationError(
            "responded_at cannot be in the future"
        )
    return responded_at


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
        "rating": row.get("rating"),
        "comment": row.get("comment"),
        "responded_at": row.get("responded_at"),
        "response_source": row.get("response_source"),
        "response_recorded_by": row.get("response_recorded_by"),
        "response_recorded": row["status"] == "responded",
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


def record_satisfaction_response(
    request_id,
    follow_up_id,
    *,
    rating,
    responded_at,
    response_source,
    comment=None,
    actor,
):
    request_id = _validate_uuid(request_id, "request_id")
    follow_up_id = _validate_uuid(follow_up_id, "follow_up_id")
    actor = _normalize_actor(actor)

    if not isinstance(rating, int) or isinstance(rating, bool):
        raise SatisfactionFollowUpValidationError(
            "rating must be an integer"
        )
    if rating < 1 or rating > 5:
        raise SatisfactionFollowUpValidationError(
            "rating must be between 1 and 5"
        )

    responded_at = _validate_responded_at(responded_at)
    response_source = _normalize_response_source(response_source)
    comment = _normalize_comment(comment)

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
                    "Satisfaction response requires request status actioned"
                )

            cur.execute(
                """
                SELECT *
                FROM service_satisfaction_followups
                WHERE request_id = %s
                  AND id = %s
                FOR UPDATE
                """,
                (request_id, follow_up_id),
            )
            follow_up = cur.fetchone()
            if follow_up is None:
                raise SatisfactionFollowUpNotFoundError(
                    "Satisfaction follow-up not found for request"
                )

            if follow_up["status"] == "responded":
                same = (
                    follow_up["rating"] == rating
                    and follow_up["comment"] == comment
                    and follow_up["responded_at"] == responded_at
                    and follow_up["response_source"] == response_source
                    and follow_up["response_recorded_by"] == actor
                )
                if same:
                    return _result(follow_up)
                raise SatisfactionFollowUpConflictError(
                    "Satisfaction response is already recorded with different evidence"
                )

            if follow_up["status"] != "prepared":
                raise SatisfactionFollowUpStateError(
                    "Satisfaction follow-up must be prepared before response"
                )

            cur.execute(
                """
                UPDATE service_satisfaction_followups
                SET status = 'responded',
                    rating = %s,
                    comment = %s,
                    responded_at = %s,
                    response_source = %s,
                    response_recorded_by = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    rating,
                    comment,
                    responded_at,
                    response_source,
                    actor,
                    follow_up_id,
                ),
            )
            responded = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="customer_satisfaction_response_recorded",
                actor=actor,
                details={
                    "follow_up_id": str(follow_up_id),
                    "delivery_status_id": str(
                        responded["delivery_status_id"]
                    ),
                    "provider_id": str(responded["provider_id"]),
                    "rating": rating,
                    "response_source": response_source,
                    "comment_present": comment is not None,
                    "review_request_created": False,
                    "complaint_created": False,
                    "rework_created": False,
                    "external_action_performed": False,
                },
            )

            return _result(responded)
