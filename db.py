import os
import uuid

import psycopg

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def get_connection():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def _record_event(
    cursor,
    request_id,
    event_type,
    actor="agent",
    details=None,
):
    event_id = uuid.uuid4()

    cursor.execute(
        """
        INSERT INTO agent_events (
            id,
            request_id,
            event_type,
            actor,
            details
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            event_id,
            request_id,
            event_type,
            actor,
            Jsonb(details or {}),
        ),
    )

    return event_id


def save_request(source, customer_name, message, result):
    request_id = uuid.uuid4()

    missing_information = result.get("missing_information", [])
    follow_up_questions = result.get("follow_up_questions", [])

    if missing_information:
        status = "needs_information"
    elif result["needs_human_review"]:
        status = "awaiting_human_review"
    else:
        status = "ready"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_requests (
                    id,
                    source,
                    customer_name,
                    message,
                    intent,
                    category,
                    summary,
                    urgency,
                    next_action,
                    needs_human_review,
                    status,
                    missing_information,
                    follow_up_questions
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                """,
                (
                    request_id,
                    source,
                    customer_name,
                    message,
                    result["intent"],
                    result["category"],
                    result["summary"],
                    result["urgency"],
                    result["next_action"],
                    result["needs_human_review"],
                    status,
                    Jsonb(missing_information),
                    Jsonb(follow_up_questions),
                ),
            )

            _record_event(
                cur,
                request_id=request_id,
                event_type="request_created",
                actor="agent",
                details={
                    "source": source,
                    "status": status,
                    "needs_human_review": result["needs_human_review"],
                    "missing_information": missing_information,
                },
            )

    return request_id


def get_request(request_id):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM agent_requests
                WHERE id = %s
                """,
                (request_id,),
            )

            return cur.fetchone()


def get_request_events(request_id):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    id,
                    request_id,
                    event_type,
                    actor,
                    details,
                    created_at
                FROM agent_events
                WHERE request_id = %s
                ORDER BY created_at ASC
                """,
                (request_id,),
            )

            return cur.fetchall()


def record_event(
    request_id,
    event_type,
    actor="agent",
    details=None,
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            return _record_event(
                cur,
                request_id=request_id,
                event_type=event_type,
                actor=actor,
                details=details,
            )


def update_request_status(
    request_id,
    new_status,
    actor,
    event_type,
    details=None,
):
    timestamp_column = {
        "approved": "approved_at",
        "rejected": "rejected_at",
        "actioned": "actioned_at",
    }.get(new_status)

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

            existing = cur.fetchone()

            if existing is None:
                return None

            if timestamp_column:
                cur.execute(
                    f"""
                    UPDATE agent_requests
                    SET status = %s,
                        {timestamp_column} = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (new_status, request_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE agent_requests
                    SET status = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (new_status, request_id),
                )

            updated_request = cur.fetchone()

            event_details = {
                "previous_status": existing["status"],
                "new_status": new_status,
            }
            event_details.update(details or {})

            _record_event(
                cur,
                request_id=request_id,
                event_type=event_type,
                actor=actor,
                details=event_details,
            )

            return updated_request