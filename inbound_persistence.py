import hashlib
import json
import uuid

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from db import get_connection
from inbound import NormalizedInboundMessage
from observability import get_correlation_id


class InboundMessageConflictError(Exception):
    """The same channel message identifier was reused for different content."""


class InboundMessageLinkConflictError(Exception):
    """An inbound message was already linked to a different internal request."""


def _canonical_payload(message: NormalizedInboundMessage) -> str:
    return json.dumps(
        message.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def inbound_payload_hash(message: NormalizedInboundMessage) -> str:
    return hashlib.sha256(_canonical_payload(message).encode("utf-8")).hexdigest()


def _sender_json(message: NormalizedInboundMessage):
    if message.sender is None:
        return None
    return message.sender.model_dump(mode="json", exclude_none=True)


def _attachments_json(message: NormalizedInboundMessage):
    return [
        attachment.model_dump(mode="json", exclude_none=True)
        for attachment in message.attachments
    ]


def _insert_inbound_message(cur, message, message_id, payload_hash):
    values = (
        message_id,
        message.schema_version,
        message.channel,
        message.text,
        Jsonb(_sender_json(message)) if message.sender is not None else None,
        message.external_message_id,
        message.external_conversation_id,
        message.occurred_at,
        message.linked_request_id,
        Jsonb(_attachments_json(message)),
        payload_hash,
        get_correlation_id(),
    )

    if message.external_message_id is None:
        cur.execute(
            """
            INSERT INTO inbound_messages (
                id,
                schema_version,
                channel,
                text,
                sender,
                external_message_id,
                external_conversation_id,
                occurred_at,
                linked_request_id,
                attachments,
                payload_hash,
                correlation_id
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            RETURNING *
            """,
            values,
        )
    else:
        cur.execute(
            """
            INSERT INTO inbound_messages (
                id,
                schema_version,
                channel,
                text,
                sender,
                external_message_id,
                external_conversation_id,
                occurred_at,
                linked_request_id,
                attachments,
                payload_hash,
                correlation_id
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (channel, external_message_id)
                WHERE external_message_id IS NOT NULL
            DO NOTHING
            RETURNING *
            """,
            values,
        )

    return cur.fetchone()


def save_inbound_message(message: NormalizedInboundMessage):
    """Persist an authenticated normalized message before downstream AI work.

    A channel/external-message pair is retry-safe. Repeating the exact same
    normalized envelope returns the existing record. Reusing that identity for
    different content fails closed.
    """

    message_id = uuid.uuid4()
    payload_hash = inbound_payload_hash(message)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            inserted = _insert_inbound_message(
                cur,
                message,
                message_id,
                payload_hash,
            )
            if inserted is not None:
                return {
                    "action": "created",
                    "message": inserted,
                }

            cur.execute(
                """
                SELECT *
                FROM inbound_messages
                WHERE channel = %s
                  AND external_message_id = %s
                """,
                (message.channel, message.external_message_id),
            )
            existing = cur.fetchone()

            if existing is None:
                raise RuntimeError("Inbound message conflict row disappeared")
            if existing["payload_hash"] != payload_hash:
                raise InboundMessageConflictError(
                    "External message identifier was reused for different content"
                )

            return {
                "action": "duplicate",
                "message": existing,
            }


def get_inbound_message(message_id):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM inbound_messages
                WHERE id = %s
                """,
                (message_id,),
            )
            return cur.fetchone()


def link_inbound_message_to_request(message_id, request_id):
    """Bind a persisted inbound record to one internal request exactly once."""

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM inbound_messages
                WHERE id = %s
                FOR UPDATE
                """,
                (message_id,),
            )
            existing = cur.fetchone()
            if existing is None:
                return None

            linked_request_id = existing["linked_request_id"]
            if linked_request_id is not None:
                if linked_request_id != request_id:
                    raise InboundMessageLinkConflictError(
                        "Inbound message is already linked to another request"
                    )
                return existing

            cur.execute(
                """
                UPDATE inbound_messages
                SET linked_request_id = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (request_id, message_id),
            )
            return cur.fetchone()
