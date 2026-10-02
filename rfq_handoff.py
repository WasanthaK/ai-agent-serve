"""Deterministic RFQ handoff preparation for Phase 5B.

This module creates durable RFQ snapshots and provider-specific prepared handoff
identities from an existing human provider selection. It performs no delivery,
provider contact, ranking, response timing, or quotation evaluation.
"""

import uuid

from psycopg.rows import dict_row

from db import get_connection, record_event_in_transaction


RFQ_PREPARABLE_REQUEST_STATUSES = frozenset({"ready", "approved"})


class RFQHandoffValidationError(ValueError):
    """RFQ handoff input is invalid before persistence."""


class RFQHandoffNotFoundError(LookupError):
    """The request or human provider selection does not exist."""


class RFQHandoffStateError(RuntimeError):
    """The request is not in a state that permits RFQ preparation."""


class RFQHandoffConflictError(RuntimeError):
    """Persisted RFQ state conflicts with the immutable selection contract."""


def _validate_uuid(value, field_name: str):
    if not isinstance(value, uuid.UUID):
        raise RFQHandoffValidationError(f"{field_name} must be a UUID")
    return value


def _normalize_actor(actor: str) -> str:
    if not isinstance(actor, str):
        raise RFQHandoffValidationError("actor must be text")
    normalized = actor.strip()
    if not normalized:
        raise RFQHandoffValidationError("actor is required")
    if len(normalized) > 200:
        raise RFQHandoffValidationError("actor is too long")
    if not normalized.startswith("operator:"):
        raise RFQHandoffValidationError(
            "RFQ preparation authority must be an operator"
        )
    return normalized


def _rfq_result(cursor, rfq):
    cursor.execute(
        """
        SELECT id, provider_id, status, created_at
        FROM rfq_provider_handoffs
        WHERE rfq_id = %s
        ORDER BY provider_id ASC
        """,
        (rfq["id"],),
    )
    handoffs = [
        {
            "handoff_id": str(row["id"]),
            "provider_id": str(row["provider_id"]),
            "status": row["status"],
            "created_at": row["created_at"],
        }
        for row in cursor.fetchall()
    ]
    handoffs.sort(key=lambda item: item["provider_id"])

    return {
        "rfq_id": str(rfq["id"]),
        "request_id": str(rfq["request_id"]),
        "selection_id": str(rfq["selection_id"]),
        "service_slug": rfq["service_slug"],
        "area_key": rfq["area_key"],
        "scope_summary": rfq["scope_summary"],
        "urgency": rfq["urgency"],
        "status": rfq["status"],
        "prepared_by": rfq["prepared_by"],
        "created_at": rfq["created_at"],
        "provider_handoffs": handoffs,
        "provider_count": len(handoffs),
        "delivery_started": False,
    }


def get_rfq_for_request(request_id):
    request_id = _validate_uuid(request_id, "request_id")

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM rfqs
                WHERE request_id = %s
                """,
                (request_id,),
            )
            rfq = cur.fetchone()
            if rfq is None:
                return None
            return _rfq_result(cur, rfq)


def prepare_rfq_handoff(request_id, *, actor: str):
    """Prepare one immutable RFQ snapshot from the human provider selection.

    Exact retries return the original RFQ. No provider contact occurs here.
    Provider-specific handoff IDs are durable identities that a later delivery
    slice may bind to response-reliability opportunities.
    """

    request_id = _validate_uuid(request_id, "request_id")
    actor = _normalize_actor(actor)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, status, summary, urgency
                FROM agent_requests
                WHERE id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            request = cur.fetchone()

            if request is None:
                raise RFQHandoffNotFoundError("Request not found")
            if request["status"] not in RFQ_PREPARABLE_REQUEST_STATUSES:
                raise RFQHandoffStateError(
                    "RFQ preparation requires request status ready or approved"
                )

            cur.execute(
                """
                SELECT *
                FROM provider_selection_decisions
                WHERE request_id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            selection = cur.fetchone()

            if selection is None:
                raise RFQHandoffNotFoundError(
                    "Human provider selection is required before RFQ preparation"
                )

            cur.execute(
                """
                SELECT provider_id
                FROM provider_selection_items
                WHERE selection_id = %s
                ORDER BY provider_id ASC
                """,
                (selection["id"],),
            )
            selected_provider_ids = [
                row["provider_id"] for row in cur.fetchall()
            ]

            if not selected_provider_ids:
                raise RFQHandoffConflictError(
                    "Human provider selection contains no providers"
                )

            cur.execute(
                """
                SELECT *
                FROM rfqs
                WHERE request_id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            existing = cur.fetchone()

            if existing is not None:
                if existing["selection_id"] != selection["id"]:
                    raise RFQHandoffConflictError(
                        "RFQ is linked to a different provider selection"
                    )
                return _rfq_result(cur, existing)

            scope_summary = request["summary"].strip()
            urgency = request["urgency"].strip()
            if not scope_summary:
                raise RFQHandoffConflictError(
                    "Request summary is required for RFQ preparation"
                )
            if not urgency:
                raise RFQHandoffConflictError(
                    "Request urgency is required for RFQ preparation"
                )

            rfq_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO rfqs (
                    id,
                    request_id,
                    selection_id,
                    service_slug,
                    area_key,
                    scope_summary,
                    urgency,
                    status,
                    prepared_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'prepared', %s)
                RETURNING *
                """,
                (
                    rfq_id,
                    request_id,
                    selection["id"],
                    selection["service_slug"],
                    selection["area_key"],
                    scope_summary,
                    urgency,
                    actor,
                ),
            )
            rfq = cur.fetchone()

            handoff_ids = []
            for provider_id in selected_provider_ids:
                handoff_id = uuid.uuid4()
                cur.execute(
                    """
                    INSERT INTO rfq_provider_handoffs (
                        id,
                        rfq_id,
                        provider_id,
                        status
                    )
                    VALUES (%s, %s, %s, 'prepared')
                    """,
                    (handoff_id, rfq_id, provider_id),
                )
                handoff_ids.append(str(handoff_id))

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="rfq_handoff_prepared",
                actor=actor,
                details={
                    "rfq_id": str(rfq_id),
                    "selection_id": str(selection["id"]),
                    "service_slug": selection["service_slug"],
                    "area_key": selection["area_key"],
                    "provider_count": len(selected_provider_ids),
                    "handoff_ids": sorted(handoff_ids),
                    "delivery_started": False,
                    "response_reliability_started": False,
                },
            )

            return _rfq_result(cur, rfq)
