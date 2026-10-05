"""Read-only factual outcome measurement for completed service requests."""

import uuid

from psycopg.rows import dict_row

from db import get_connection


class OutcomeMeasurementValidationError(ValueError):
    pass


class OutcomeMeasurementNotFoundError(LookupError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise OutcomeMeasurementValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def get_outcome_measurement(request_id):
    request_id = _validate_uuid(request_id, "request_id")

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    r.id AS request_id,
                    r.status AS request_status,
                    s.id AS delivery_status_id,
                    s.provider_id,
                    s.status AS delivery_status,
                    s.completed_at,
                    f.id AS satisfaction_follow_up_id,
                    f.status AS satisfaction_status,
                    f.rating AS satisfaction_rating,
                    f.responded_at,
                    EXISTS (
                        SELECT 1
                        FROM service_review_requests rr
                        WHERE rr.request_id = r.id
                    ) AS review_request_prepared,
                    (
                        SELECT COUNT(*)
                        FROM service_delivery_exceptions e
                        WHERE e.request_id = r.id
                    ) AS delivery_exception_count,
                    (
                        SELECT COUNT(*)
                        FROM service_delivery_interventions i
                        WHERE i.request_id = r.id
                    ) AS intervention_count,
                    (
                        SELECT COUNT(*)
                        FROM service_delivery_interventions i
                        WHERE i.request_id = r.id
                          AND i.status = 'open'
                    ) AS open_intervention_count,
                    EXISTS (
                        SELECT 1
                        FROM service_closure_escalations ce
                        WHERE ce.request_id = r.id
                          AND ce.escalation_kind = 'complaint'
                    ) AS complaint_present,
                    EXISTS (
                        SELECT 1
                        FROM service_closure_escalations ce
                        WHERE ce.request_id = r.id
                          AND ce.escalation_kind = 'rework'
                    ) AS rework_present
                FROM agent_requests r
                LEFT JOIN service_delivery_status s
                    ON s.request_id = r.id
                LEFT JOIN service_satisfaction_followups f
                    ON f.request_id = r.id
                WHERE r.id = %s
                """,
                (request_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise OutcomeMeasurementNotFoundError("Request not found")

    return {
        "request_id": str(row["request_id"]),
        "request_status": row["request_status"],
        "delivery_status_id": (
            None
            if row["delivery_status_id"] is None
            else str(row["delivery_status_id"])
        ),
        "provider_id": (
            None
            if row["provider_id"] is None
            else str(row["provider_id"])
        ),
        "delivery_status": row["delivery_status"],
        "delivery_completed": row["delivery_status"] == "completed",
        "completed_at": row["completed_at"],
        "satisfaction_follow_up_id": (
            None
            if row["satisfaction_follow_up_id"] is None
            else str(row["satisfaction_follow_up_id"])
        ),
        "satisfaction_status": row["satisfaction_status"],
        "satisfaction_response_recorded": (
            row["satisfaction_status"] == "responded"
        ),
        "satisfaction_rating": row["satisfaction_rating"],
        "satisfaction_responded_at": row["responded_at"],
        "review_request_prepared": bool(
            row["review_request_prepared"]
        ),
        "delivery_exception_count": row["delivery_exception_count"],
        "intervention_count": row["intervention_count"],
        "open_intervention_count": row["open_intervention_count"],
        "complaint_present": bool(row["complaint_present"]),
        "rework_present": bool(row["rework_present"]),
        "score": None,
        "provider_rank": None,
        "policy_change_applied": False,
        "training_signal_applied": False,
        "external_action_performed": False,
    }
