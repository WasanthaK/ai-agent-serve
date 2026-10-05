"""Human intervention queue for delivery exceptions.

Creates one human-owned intervention item per recorded delivery exception and
supports acknowledgement. It does not resolve the exception, change delivery
state, send notifications, or perform external actions.
"""

import uuid

from psycopg.rows import dict_row

from db import get_connection, record_event_in_transaction


ALLOWED_PRIORITIES = frozenset({"normal", "high", "urgent"})


class HumanInterventionValidationError(ValueError):
    pass


class HumanInterventionNotFoundError(LookupError):
    pass


class HumanInterventionStateError(RuntimeError):
    pass


class HumanInterventionConflictError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise HumanInterventionValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise HumanInterventionValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise HumanInterventionValidationError("actor is required")
    if len(actor) > 200:
        raise HumanInterventionValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise HumanInterventionValidationError(
            "Human intervention authority must be an operator"
        )
    return actor


def _normalize_reason(reason, field_name):
    if not isinstance(reason, str):
        raise HumanInterventionValidationError(
            f"{field_name} must be text"
        )
    reason = reason.strip()
    if not reason:
        raise HumanInterventionValidationError(
            f"{field_name} is required"
        )
    if len(reason) > 2000:
        raise HumanInterventionValidationError(
            f"{field_name} is too long"
        )
    return reason


def _normalize_priority(priority):
    if not isinstance(priority, str):
        raise HumanInterventionValidationError("priority must be text")
    priority = priority.strip().lower()
    if priority not in ALLOWED_PRIORITIES:
        raise HumanInterventionValidationError(
            "priority must be normal, high, or urgent"
        )
    return priority


def _result(row):
    return {
        "intervention_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "exception_id": str(row["exception_id"]),
        "delivery_status_id": str(row["delivery_status_id"]),
        "provider_id": str(row["provider_id"]),
        "priority": row["priority"],
        "reason": row["reason"],
        "status": row["status"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "acknowledged_by": row["acknowledged_by"],
        "acknowledgement_reason": row["acknowledgement_reason"],
        "acknowledged_at": row["acknowledged_at"],
        "updated_at": row["updated_at"],
        "exception_resolved": False,
        "delivery_status_changed": False,
        "notification_sent": False,
    }


def get_human_interventions(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_delivery_interventions
                WHERE request_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (request_id,),
            )
            return [_result(row) for row in cur.fetchall()]


def create_human_intervention(
    request_id,
    exception_id,
    *,
    priority,
    reason,
    actor,
):
    request_id = _validate_uuid(request_id, "request_id")
    exception_id = _validate_uuid(exception_id, "exception_id")
    priority = _normalize_priority(priority)
    reason = _normalize_reason(reason, "reason")
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
                raise HumanInterventionNotFoundError("Request not found")
            if request["status"] != "actioned":
                raise HumanInterventionStateError(
                    "Human intervention requires request status actioned"
                )

            cur.execute(
                """
                SELECT
                    e.*,
                    s.status AS delivery_status
                FROM service_delivery_exceptions e
                INNER JOIN service_delivery_status s
                    ON s.id = e.delivery_status_id
                WHERE e.request_id = %s
                  AND e.id = %s
                FOR UPDATE OF e, s
                """,
                (request_id, exception_id),
            )
            exception = cur.fetchone()
            if exception is None:
                raise HumanInterventionNotFoundError(
                    "Delivery exception not found for request"
                )
            if exception["delivery_status"] not in {
                "scheduled",
                "in_progress",
            }:
                raise HumanInterventionStateError(
                    "Human intervention requires active delivery"
                )

            cur.execute(
                """
                SELECT *
                FROM service_delivery_interventions
                WHERE exception_id = %s
                FOR UPDATE
                """,
                (exception_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                if (
                    existing["priority"] == priority
                    and existing["reason"] == reason
                    and existing["created_by"] == actor
                ):
                    return _result(existing)
                raise HumanInterventionConflictError(
                    "A different intervention already exists for exception"
                )

            intervention_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO service_delivery_interventions (
                    id,
                    request_id,
                    exception_id,
                    delivery_status_id,
                    provider_id,
                    priority,
                    reason,
                    created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    intervention_id,
                    request_id,
                    exception_id,
                    exception["delivery_status_id"],
                    exception["provider_id"],
                    priority,
                    reason,
                    actor,
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="human_intervention_created",
                actor=actor,
                details={
                    "intervention_id": str(intervention_id),
                    "exception_id": str(exception_id),
                    "delivery_status_id": str(
                        exception["delivery_status_id"]
                    ),
                    "provider_id": str(exception["provider_id"]),
                    "priority": priority,
                    "status": "open",
                    "exception_resolved": False,
                    "delivery_status_changed": False,
                    "notification_sent": False,
                },
            )

            return _result(created)


def acknowledge_human_intervention(
    request_id,
    intervention_id,
    *,
    reason,
    actor,
):
    request_id = _validate_uuid(request_id, "request_id")
    intervention_id = _validate_uuid(intervention_id, "intervention_id")
    reason = _normalize_reason(reason, "acknowledgement_reason")
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
                raise HumanInterventionNotFoundError("Request not found")
            if request["status"] != "actioned":
                raise HumanInterventionStateError(
                    "Human intervention acknowledgement requires actioned request"
                )

            cur.execute(
                """
                SELECT *
                FROM service_delivery_interventions
                WHERE request_id = %s
                  AND id = %s
                FOR UPDATE
                """,
                (request_id, intervention_id),
            )
            current = cur.fetchone()
            if current is None:
                raise HumanInterventionNotFoundError(
                    "Human intervention not found for request"
                )

            if current["status"] == "acknowledged":
                if (
                    current["acknowledged_by"] == actor
                    and current["acknowledgement_reason"] == reason
                ):
                    return _result(current)
                raise HumanInterventionConflictError(
                    "Intervention is already acknowledged with different evidence"
                )

            if current["status"] != "open":
                raise HumanInterventionStateError(
                    "Intervention must be open before acknowledgement"
                )

            cur.execute(
                """
                UPDATE service_delivery_interventions
                SET status = 'acknowledged',
                    acknowledged_by = %s,
                    acknowledgement_reason = %s,
                    acknowledged_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (actor, reason, intervention_id),
            )
            acknowledged = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="human_intervention_acknowledged",
                actor=actor,
                details={
                    "intervention_id": str(intervention_id),
                    "exception_id": str(acknowledged["exception_id"]),
                    "previous_status": "open",
                    "new_status": "acknowledged",
                    "exception_resolved": False,
                    "delivery_status_changed": False,
                    "notification_sent": False,
                },
            )

            return _result(acknowledged)
