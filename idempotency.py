"""Persistent idempotency reservations for inbound webhook delivery."""

import hashlib
import json
import logging
import uuid

from psycopg.rows import dict_row

from db import get_connection


recovery_logger = logging.getLogger("agent.idempotency")
recovery_logger.setLevel(logging.INFO)
if not recovery_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    recovery_logger.addHandler(_handler)
recovery_logger.propagate = False


def hash_idempotency_key(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_webhook_payload(source, customer_name, message):
    canonical = json.dumps(
        {
            "source": source,
            "customer_name": customer_name,
            "message": message,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def reserve_webhook_delivery(source, key_hash, payload_hash):
    for _ in range(3):
        request_id = uuid.uuid4()

        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO webhook_idempotency (
                        source,
                        idempotency_key_hash,
                        payload_hash,
                        request_id,
                        state
                    )
                    VALUES (%s, %s, %s, %s, 'processing')
                    ON CONFLICT (source, idempotency_key_hash) DO NOTHING
                    RETURNING request_id, payload_hash, state
                    """,
                    (source, key_hash, payload_hash, request_id),
                )
                inserted = cur.fetchone()
                if inserted is not None:
                    return {
                        "action": "process",
                        "request_id": inserted["request_id"],
                    }

                cur.execute(
                    """
                    SELECT request_id, payload_hash, state
                    FROM webhook_idempotency
                    WHERE source = %s
                      AND idempotency_key_hash = %s
                    """,
                    (source, key_hash),
                )
                existing = cur.fetchone()

        if existing is None:
            # The owning delivery may have failed and released its reservation
            # between our conflict check and lookup. Retry acquisition.
            continue

        if existing["payload_hash"] != payload_hash:
            return {
                "action": "conflict",
                "request_id": existing["request_id"],
            }

        return {
            "action": existing["state"],
            "request_id": existing["request_id"],
        }

    raise RuntimeError("Idempotency reservation changed repeatedly")


def complete_webhook_delivery(source, key_hash, request_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE webhook_idempotency
                SET state = 'completed',
                    updated_at = NOW()
                WHERE source = %s
                  AND idempotency_key_hash = %s
                  AND request_id = %s
                  AND state = 'processing'
                """,
                (source, key_hash, request_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError("Idempotency reservation could not be completed")


def release_webhook_delivery(source, key_hash, request_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM webhook_idempotency
                WHERE source = %s
                  AND idempotency_key_hash = %s
                  AND request_id = %s
                  AND state = 'processing'
                """,
                (source, key_hash, request_id),
            )


def recover_incomplete_webhook_deliveries():
    """Reconcile reservations left in processing by an interrupted agent.

    This is intended to run once during single-agent application startup,
    before inbound requests are accepted. PostgreSQL commit state is the source
    of truth: a reservation whose request row exists is completed; otherwise
    the reservation is released so the delivery can be retried.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE webhook_idempotency AS wi
                SET state = 'completed',
                    updated_at = NOW()
                WHERE wi.state = 'processing'
                  AND EXISTS (
                      SELECT 1
                      FROM agent_requests AS ar
                      WHERE ar.id = wi.request_id
                  )
                """
            )
            completed = cur.rowcount

            cur.execute(
                """
                DELETE FROM webhook_idempotency AS wi
                WHERE wi.state = 'processing'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM agent_requests AS ar
                      WHERE ar.id = wi.request_id
                  )
                """
            )
            released = cur.rowcount

    result = {
        "completed": completed,
        "released": released,
    }
    recovery_logger.info(
        json.dumps(
            {
                "event": "idempotency_recovery_completed",
                **result,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return result
