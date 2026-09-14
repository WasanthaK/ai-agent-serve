import os
import uuid
import psycopg


def get_connection():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def save_request(source, customer_name, message, result):
    request_id = uuid.uuid4()

    status = (
        "awaiting_human_review"
        if result["needs_human_review"]
        else "ready"
    )

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
                    status
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
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
                ),
            )

    return request_id
