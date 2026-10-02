"""Human-authorized provider selection for Phase 5B.

Selection is an immutable set chosen from the current deterministic eligible
provider set. It does not rank providers and it performs no provider contact.
"""

import uuid

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from db import get_connection, record_event_in_transaction
from provider_directory import (
    ProviderDirectoryValidationError,
    list_eligible_providers_for_service_and_area_with_cursor,
)


SELECTABLE_REQUEST_STATUSES = frozenset({"ready", "approved"})
MAX_SELECTED_PROVIDERS = 20


class ProviderSelectionValidationError(ValueError):
    """Provider-selection input is invalid before persistence."""


class ProviderSelectionNotFoundError(LookupError):
    """The request does not exist."""


class ProviderSelectionStateError(RuntimeError):
    """The request is not in a state that permits human provider selection."""


class ProviderSelectionEligibilityError(RuntimeError):
    """At least one selected provider is outside the current eligible set."""


class ProviderSelectionConflictError(RuntimeError):
    """A different immutable selection already exists for this request."""


def _validate_uuid(value, field_name: str):
    if not isinstance(value, uuid.UUID):
        raise ProviderSelectionValidationError(f"{field_name} must be a UUID")
    return value


def _normalize_actor(actor: str) -> str:
    if not isinstance(actor, str):
        raise ProviderSelectionValidationError("actor must be text")
    normalized = actor.strip()
    if not normalized:
        raise ProviderSelectionValidationError("actor is required")
    if len(normalized) > 200:
        raise ProviderSelectionValidationError("actor is too long")
    return normalized


def _normalize_reason(reason):
    if reason is None:
        return None
    if not isinstance(reason, str):
        raise ProviderSelectionValidationError("reason must be text")
    normalized = reason.strip()
    if not normalized:
        return None
    if len(normalized) > 1000:
        raise ProviderSelectionValidationError(
            "reason must be at most 1000 characters"
        )
    return normalized


def _normalize_provider_ids(provider_ids):
    if not isinstance(provider_ids, (list, tuple)):
        raise ProviderSelectionValidationError(
            "provider_ids must be a list or tuple"
        )
    if not provider_ids:
        raise ProviderSelectionValidationError(
            "At least one provider must be selected"
        )
    if len(provider_ids) > MAX_SELECTED_PROVIDERS:
        raise ProviderSelectionValidationError(
            f"At most {MAX_SELECTED_PROVIDERS} providers may be selected"
        )

    normalized = []
    seen = set()
    for provider_id in provider_ids:
        provider_id = _validate_uuid(provider_id, "provider_id")
        if provider_id in seen:
            raise ProviderSelectionValidationError(
                "provider_ids must not contain duplicates"
            )
        seen.add(provider_id)
        normalized.append(provider_id)

    return tuple(normalized)


def _selection_result(cursor, decision):
    cursor.execute(
        """
        SELECT provider_id
        FROM provider_selection_items
        WHERE selection_id = %s
        ORDER BY provider_id ASC
        """,
        (decision["id"],),
    )
    selected_provider_ids = [
        str(row["provider_id"]) for row in cursor.fetchall()
    ]

    return {
        "selection_id": str(decision["id"]),
        "request_id": str(decision["request_id"]),
        "service_slug": decision["service_slug"],
        "area_key": decision["area_key"],
        "eligible_provider_ids": list(decision["eligible_provider_ids"]),
        "selected_provider_ids": selected_provider_ids,
        "selected_by": decision["selected_by"],
        "reason": decision["reason"],
        "created_at": decision["created_at"],
        "ranked": False,
        "selection_authority": "human",
    }


def get_provider_selection(request_id):
    _validate_uuid(request_id, "request_id")

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM provider_selection_decisions
                WHERE request_id = %s
                """,
                (request_id,),
            )
            decision = cur.fetchone()
            if decision is None:
                return None
            return _selection_result(cur, decision)


def select_providers_for_request(
    request_id,
    service_slug: str,
    area_key: str,
    provider_ids,
    *,
    actor: str,
    reason=None,
):
    """Record one immutable human selection set for an actionable request.

    The candidate set is rebuilt inside this database transaction and locked until
    the selection and audit event commit. An exact retry is idempotent; a different
    retry fails closed.
    """

    request_id = _validate_uuid(request_id, "request_id")
    selected_ids = _normalize_provider_ids(provider_ids)
    actor = _normalize_actor(actor)
    reason = _normalize_reason(reason)

    try:
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
                    raise ProviderSelectionNotFoundError("Request not found")
                if request["status"] not in SELECTABLE_REQUEST_STATUSES:
                    raise ProviderSelectionStateError(
                        "Provider selection requires request status ready or approved"
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
                existing = cur.fetchone()

                selected_set = set(selected_ids)
                selected_snapshot = sorted(str(provider_id) for provider_id in selected_set)

                if existing is not None:
                    result = _selection_result(cur, existing)
                    same = (
                        existing["service_slug"] == service_slug
                        and existing["area_key"] == area_key
                        and result["selected_provider_ids"] == selected_snapshot
                        and existing["selected_by"] == actor
                        and existing["reason"] == reason
                    )
                    if same:
                        return result
                    raise ProviderSelectionConflictError(
                        "A different provider selection already exists for this request"
                    )

                eligible = list_eligible_providers_for_service_and_area_with_cursor(
                    cur,
                    service_slug,
                    area_key,
                    lock_rows=True,
                )
                eligible_ids = {provider["id"] for provider in eligible}

                if not selected_set.issubset(eligible_ids):
                    raise ProviderSelectionEligibilityError(
                        "Selected providers must all be currently eligible"
                    )

                eligible_snapshot = sorted(str(provider_id) for provider_id in eligible_ids)

                selection_id = uuid.uuid4()
                cur.execute(
                    """
                    INSERT INTO provider_selection_decisions (
                        id,
                        request_id,
                        service_slug,
                        area_key,
                        eligible_provider_ids,
                        selected_by,
                        reason
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        selection_id,
                        request_id,
                        service_slug,
                        area_key,
                        Jsonb(eligible_snapshot),
                        actor,
                        reason,
                    ),
                )
                decision = cur.fetchone()

                for provider_id in selected_ids:
                    cur.execute(
                        """
                        INSERT INTO provider_selection_items (
                            selection_id,
                            provider_id
                        )
                        VALUES (%s, %s)
                        """,
                        (selection_id, provider_id),
                    )

                record_event_in_transaction(
                    cur,
                    request_id=request_id,
                    event_type="provider_selection_recorded",
                    actor=actor,
                    details={
                        "selection_id": str(selection_id),
                        "service_slug": service_slug,
                        "area_key": area_key,
                        "eligible_provider_ids": eligible_snapshot,
                        "selected_provider_ids": selected_snapshot,
                        "selected_provider_count": len(selected_snapshot),
                        "reason_present": reason is not None,
                        "ranked": False,
                        "selection_authority": "human",
                    },
                )

                return _selection_result(cur, decision)
    except ProviderDirectoryValidationError as exc:
        raise ProviderSelectionValidationError(str(exc)) from exc
