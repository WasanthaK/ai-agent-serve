"""Human-owned complaint and rework escalation foundation.

Creates durable complaint/rework escalation records from recorded satisfaction
evidence. It does not infer escalation from rating, reopen delivery, dispatch
rework, notify anyone, or perform an external action.
"""

import uuid

from psycopg.rows import dict_row

from db import get_connection, record_event_in_transaction


ALLOWED_ESCALATION_KINDS = frozenset({"complaint", "rework"})
ALLOWED_PRIORITIES = frozenset({"normal", "high", "urgent"})


class ClosureEscalationValidationError(ValueError):
    pass


class ClosureEscalationNotFoundError(LookupError):
    pass


class ClosureEscalationStateError(RuntimeError):
    pass


class ClosureEscalationConflictError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise ClosureEscalationValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise ClosureEscalationValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise ClosureEscalationValidationError("actor is required")
    if len(actor) > 200:
        raise ClosureEscalationValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise ClosureEscalationValidationError(
            "Closure escalation authority must be an operator"
        )
    return actor


def _normalize_kind(escalation_kind):
    if not isinstance(escalation_kind, str):
        raise ClosureEscalationValidationError(
            "escalation_kind must be text"
        )
    escalation_kind = escalation_kind.strip().lower()
    if escalation_kind not in ALLOWED_ESCALATION_KINDS:
        raise ClosureEscalationValidationError(
            "escalation_kind must be complaint or rework"
        )
    return escalation_kind


def _normalize_priority(priority):
    if not isinstance(priority, str):
        raise ClosureEscalationValidationError("priority must be text")
    priority = priority.strip().lower()
    if priority not in ALLOWED_PRIORITIES:
        raise ClosureEscalationValidationError(
            "priority must be normal, high, or urgent"
        )
    return priority


def _normalize_reason(reason):
    if not isinstance(reason, str):
        raise ClosureEscalationValidationError("reason must be text")
    reason = reason.strip()
    if not reason:
        raise ClosureEscalationValidationError("reason is required")
    if len(reason) > 4000:
        raise ClosureEscalationValidationError("reason is too long")
    return reason


def _result(row):
    return {
        "escalation_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "satisfaction_follow_up_id": str(
            row["satisfaction_follow_up_id"]
        ),
        "provider_id": str(row["provider_id"]),
        "escalation_kind": row["escalation_kind"],
        "priority": row["priority"],
        "reason": row["reason"],
        "status": row["status"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "auto_triggered": False,
        "delivery_reopened": False,
        "rework_dispatched": False,
        "notification_sent": False,
        "external_action_performed": False,
    }


def get_closure_escalations(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_closure_escalations
                WHERE request_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (request_id,),
            )
            return [_result(row) for row in cur.fetchall()]


def create_closure_escalation(
    request_id,
    satisfaction_follow_up_id,
    escalation_kind,
    *,
    priority,
    reason,
    actor,
):
    request_id = _validate_uuid(request_id, "request_id")
    satisfaction_follow_up_id = _validate_uuid(
        satisfaction_follow_up_id,
        "satisfaction_follow_up_id",
    )
    escalation_kind = _normalize_kind(escalation_kind)
    priority = _normalize_priority(priority)
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
                raise ClosureEscalationNotFoundError("Request not found")
            if request["status"] != "actioned":
                raise ClosureEscalationStateError(
                    "Closure escalation requires request status actioned"
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
                raise ClosureEscalationNotFoundError(
                    "Satisfaction follow-up not found for request"
                )
            if satisfaction["status"] != "responded":
                raise ClosureEscalationStateError(
                    "Closure escalation requires recorded satisfaction response"
                )

            cur.execute(
                """
                SELECT *
                FROM service_closure_escalations
                WHERE request_id = %s
                  AND escalation_kind = %s
                FOR UPDATE
                """,
                (request_id, escalation_kind),
            )
            existing = cur.fetchone()
            if existing is not None:
                same = (
                    existing["satisfaction_follow_up_id"]
                    == satisfaction_follow_up_id
                    and existing["priority"] == priority
                    and existing["reason"] == reason
                    and existing["created_by"] == actor
                )
                if same:
                    return _result(existing)
                raise ClosureEscalationConflictError(
                    "A different escalation already exists for this kind"
                )

            escalation_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO service_closure_escalations (
                    id,
                    request_id,
                    satisfaction_follow_up_id,
                    provider_id,
                    escalation_kind,
                    priority,
                    reason,
                    created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    escalation_id,
                    request_id,
                    satisfaction_follow_up_id,
                    satisfaction["provider_id"],
                    escalation_kind,
                    priority,
                    reason,
                    actor,
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="closure_escalation_created",
                actor=actor,
                details={
                    "escalation_id": str(escalation_id),
                    "satisfaction_follow_up_id": str(
                        satisfaction_follow_up_id
                    ),
                    "provider_id": str(satisfaction["provider_id"]),
                    "escalation_kind": escalation_kind,
                    "priority": priority,
                    "satisfaction_rating": satisfaction["rating"],
                    "auto_triggered": False,
                    "delivery_reopened": False,
                    "rework_dispatched": False,
                    "notification_sent": False,
                    "external_action_performed": False,
                },
            )

            return _result(created)
