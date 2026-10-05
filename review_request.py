"""Preparation-only public review request.

Creates one durable public-review request from recorded satisfaction evidence.
It does not gate on rating, resolve a review platform/link, send a message, or
perform an external action.
"""

import uuid

from psycopg.rows import dict_row

from db import get_connection, record_event_in_transaction


REVIEW_REQUEST_MESSAGE = (
    "Would you be willing to share a public review of your service experience?"
)


class ReviewRequestValidationError(ValueError):
    pass


class ReviewRequestNotFoundError(LookupError):
    pass


class ReviewRequestStateError(RuntimeError):
    pass


class ReviewRequestConflictError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise ReviewRequestValidationError(f"{field_name} must be a UUID")
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise ReviewRequestValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise ReviewRequestValidationError("actor is required")
    if len(actor) > 200:
        raise ReviewRequestValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise ReviewRequestValidationError(
            "Review request authority must be an operator"
        )
    return actor


def _normalize_reason(reason):
    if not isinstance(reason, str):
        raise ReviewRequestValidationError("reason must be text")
    reason = reason.strip()
    if not reason:
        raise ReviewRequestValidationError("reason is required")
    if len(reason) > 2000:
        raise ReviewRequestValidationError("reason is too long")
    return reason


def _result(row):
    return {
        "review_request_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "satisfaction_follow_up_id": str(
            row["satisfaction_follow_up_id"]
        ),
        "provider_id": str(row["provider_id"]),
        "purpose": row["purpose"],
        "message": row["message"],
        "target_platform": row["target_platform"],
        "target_url": row["target_url"],
        "destination_channel": row["destination_channel"],
        "destination_address": row["destination_address"],
        "status": row["status"],
        "prepared_reason": row["prepared_reason"],
        "prepared_by": row["prepared_by"],
        "created_at": row["created_at"],
        "rating_gated": False,
        "sent": False,
        "external_action_performed": False,
    }


def get_review_request(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_review_requests
                WHERE request_id = %s
                """,
                (request_id,),
            )
            row = cur.fetchone()
            return None if row is None else _result(row)


def prepare_review_request(
    request_id,
    satisfaction_follow_up_id,
    *,
    reason,
    actor,
):
    request_id = _validate_uuid(request_id, "request_id")
    satisfaction_follow_up_id = _validate_uuid(
        satisfaction_follow_up_id,
        "satisfaction_follow_up_id",
    )
    reason = _normalize_reason(reason)
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
                raise ReviewRequestNotFoundError("Request not found")
            if request["status"] != "actioned":
                raise ReviewRequestStateError(
                    "Review request requires request status actioned"
                )

            cur.execute(
                """
                SELECT *
                FROM service_satisfaction_followups
                WHERE request_id = %s
                  AND id = %s
                FOR UPDATE
                """,
                (request_id, satisfaction_follow_up_id),
            )
            satisfaction = cur.fetchone()
            if satisfaction is None:
                raise ReviewRequestNotFoundError(
                    "Satisfaction follow-up not found for request"
                )
            if satisfaction["status"] != "responded":
                raise ReviewRequestStateError(
                    "Review request requires a recorded satisfaction response"
                )

            cur.execute(
                """
                SELECT *
                FROM service_review_requests
                WHERE request_id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                same = (
                    existing["satisfaction_follow_up_id"]
                    == satisfaction_follow_up_id
                    and existing["prepared_reason"] == reason
                    and existing["prepared_by"] == actor
                )
                if same:
                    return _result(existing)
                raise ReviewRequestConflictError(
                    "A different review request already exists for request"
                )

            review_request_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO service_review_requests (
                    id,
                    request_id,
                    satisfaction_follow_up_id,
                    provider_id,
                    message,
                    prepared_reason,
                    prepared_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    review_request_id,
                    request_id,
                    satisfaction_follow_up_id,
                    satisfaction["provider_id"],
                    REVIEW_REQUEST_MESSAGE,
                    reason,
                    actor,
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="public_review_request_prepared",
                actor=actor,
                details={
                    "review_request_id": str(review_request_id),
                    "satisfaction_follow_up_id": str(
                        satisfaction_follow_up_id
                    ),
                    "provider_id": str(satisfaction["provider_id"]),
                    "satisfaction_rating": satisfaction["rating"],
                    "rating_gated": False,
                    "target_resolved": False,
                    "destination_resolved": False,
                    "sent": False,
                    "external_action_performed": False,
                },
            )

            return _result(created)
