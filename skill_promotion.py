"""Controlled human promotion of regression-passed skill changes.

Promotion is the only Phase 7 operation that changes live model instructions.
It is deterministic, human-authorized, versioned, durable, restart-restorable,
and gated by exact passing regression evidence.
"""

import re
import uuid
from dataclasses import replace
from threading import Lock

from psycopg.rows import dict_row

from agent_skills import skill_registry
from db import get_connection, record_event_in_transaction


_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_PROMOTION_LOCK = Lock()


class SkillPromotionValidationError(ValueError):
    pass


class SkillPromotionNotFoundError(LookupError):
    pass


class SkillPromotionStateError(RuntimeError):
    pass


class SkillPromotionConflictError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise SkillPromotionValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise SkillPromotionValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise SkillPromotionValidationError("actor is required")
    if len(actor) > 200:
        raise SkillPromotionValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise SkillPromotionValidationError(
            "Skill promotion authority must be an operator"
        )
    return actor


def _normalize_text(value, field_name, max_length):
    if not isinstance(value, str):
        raise SkillPromotionValidationError(
            f"{field_name} must be text"
        )
    value = value.strip()
    if not value:
        raise SkillPromotionValidationError(
            f"{field_name} is required"
        )
    if len(value) > max_length:
        raise SkillPromotionValidationError(
            f"{field_name} is too long"
        )
    return value


def _next_minor_version(version):
    match = _VERSION_RE.fullmatch(version)
    if match is None:
        raise SkillPromotionStateError(
            "Base skill version is not semantic x.y.z"
        )
    major, minor, _patch = (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
    )
    return f"{major}.{minor + 1}.0"


def _promoted_instructions(
    base_instructions,
    change_scope,
    amendment,
):
    label = (
        "Approved instruction amendment"
        if change_scope == "instructions"
        else "Approved model-policy amendment"
    )
    return (
        base_instructions.strip()
        + "\n\n"
        + f"## {label}\n"
        + amendment.strip()
    )


def _row_result(row):
    return {
        "promotion_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "proposal_id": str(row["proposal_id"]),
        "revision_id": (
            str(row["revision_id"])
            if row["revision_id"] is not None
            else None
        ),
        "regression_test_id": str(row["regression_test_id"]),
        "skill_name": row["skill_name"],
        "base_skill_version": row["base_skill_version"],
        "promoted_skill_version": row["promoted_skill_version"],
        "change_scope": row["change_scope"],
        "reason": row["reason"],
        "promoted_by": row["promoted_by"],
        "created_at": row["created_at"],
        "promotion_applied": True,
        "skill_version_changed": True,
        "registry_changed": True,
        "production_behaviour_changed": True,
    }


def _activate_promotion(row, registry):
    current = registry.get(row["skill_name"])

    if (
        current.version == row["promoted_skill_version"]
        and current.instructions.strip()
        == row["promoted_instructions"].strip()
    ):
        return current

    if current.version != row["base_skill_version"]:
        raise SkillPromotionStateError(
            "Runtime skill version does not match promotion base"
        )
    if (
        current.instructions.strip()
        != row["base_instructions_snapshot"].strip()
    ):
        raise SkillPromotionStateError(
            "Runtime skill instructions do not match promotion base snapshot"
        )

    promoted = replace(
        current,
        version=row["promoted_skill_version"],
        instructions=row["promoted_instructions"],
    )
    registry.replace(
        promoted,
        expected_version=row["base_skill_version"],
        expected_instructions=row["base_instructions_snapshot"],
    )
    return promoted


def get_skill_promotions(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_skill_promotions
                WHERE request_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (request_id,),
            )
            return [_row_result(row) for row in cur.fetchall()]


def load_active_skill_promotions(registry=skill_registry):
    """Restore all durable promotions into a fresh runtime registry."""
    with _PROMOTION_LOCK:
        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM service_skill_promotions
                    ORDER BY created_at ASC, id ASC
                    """
                )
                promotions = cur.fetchall()

        for promotion in promotions:
            _activate_promotion(promotion, registry)

        return len(promotions)


def promote_skill(
    request_id,
    regression_test_id,
    *,
    reason,
    actor,
    registry=skill_registry,
):
    request_id = _validate_uuid(request_id, "request_id")
    regression_test_id = _validate_uuid(
        regression_test_id,
        "regression_test_id",
    )
    reason = _normalize_text(reason, "reason", 4000)
    actor = _normalize_actor(actor)

    with _PROMOTION_LOCK:
        result_row = None

        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        t.*,
                        p.status AS proposal_status,
                        p.base_instructions_snapshot,
                        p.proposed_change AS proposal_change,
                        p.rationale AS proposal_rationale
                    FROM service_skill_regression_tests t
                    JOIN service_skill_improvement_proposals p
                      ON p.id = t.proposal_id
                    WHERE t.request_id = %s
                      AND t.id = %s
                    FOR UPDATE OF t, p
                    """,
                    (request_id, regression_test_id),
                )
                evidence = cur.fetchone()
                if evidence is None:
                    raise SkillPromotionNotFoundError(
                        "Passing regression evidence not found for request"
                    )

                cur.execute(
                    """
                    SELECT *
                    FROM service_skill_promotions
                    WHERE proposal_id = %s
                       OR regression_test_id = %s
                    FOR UPDATE
                    """,
                    (
                        evidence["proposal_id"],
                        regression_test_id,
                    ),
                )
                existing = cur.fetchone()
                if existing is not None:
                    same = (
                        existing["request_id"] == request_id
                        and existing["regression_test_id"]
                        == regression_test_id
                        and existing["reason"] == reason
                        and existing["promoted_by"] == actor
                    )
                    if not same:
                        raise SkillPromotionConflictError(
                            "A different promotion already exists for this proposal"
                        )
                    result_row = existing
                else:
                    if evidence["proposal_status"] != "proposed":
                        raise SkillPromotionStateError(
                            "Promotion requires a proposed improvement"
                        )
                    if evidence["verdict"] != "pass":
                        raise SkillPromotionStateError(
                            "Promotion requires passing regression evidence"
                        )

                    revision = None
                    cur.execute(
                        """
                        SELECT *
                        FROM service_skill_improvement_revisions
                        WHERE proposal_id = %s
                        ORDER BY revision_number DESC
                        LIMIT 1
                        FOR UPDATE
                        """,
                        (evidence["proposal_id"],),
                    )
                    revision = cur.fetchone()

                    if revision is None:
                        if evidence["revision_id"] is not None:
                            raise SkillPromotionStateError(
                                "Regression evidence references an unknown revision"
                            )
                        amendment = evidence["proposal_change"]
                    else:
                        if evidence["revision_id"] != revision["id"]:
                            raise SkillPromotionStateError(
                                "Promotion requires passing regression evidence for the latest revision"
                            )
                        amendment = revision["proposed_change"]

                    current = registry.get(evidence["skill_name"])
                    if current.version != evidence["base_skill_version"]:
                        raise SkillPromotionStateError(
                            "Current registered skill version differs from promotion base version"
                        )
                    if (
                        current.instructions.strip()
                        != evidence["base_instructions_snapshot"].strip()
                    ):
                        raise SkillPromotionStateError(
                            "Current registered skill instructions differ from promotion base snapshot"
                        )

                    new_version = _next_minor_version(
                        evidence["base_skill_version"]
                    )
                    promoted_instructions = _promoted_instructions(
                        evidence["base_instructions_snapshot"],
                        evidence["change_scope"],
                        amendment,
                    )

                    promotion_id = uuid.uuid4()
                    cur.execute(
                        """
                        INSERT INTO service_skill_promotions (
                            id,
                            request_id,
                            proposal_id,
                            revision_id,
                            regression_test_id,
                            skill_name,
                            base_skill_version,
                            promoted_skill_version,
                            change_scope,
                            base_instructions_snapshot,
                            promoted_instructions,
                            reason,
                            promoted_by
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s
                        )
                        RETURNING *
                        """,
                        (
                            promotion_id,
                            request_id,
                            evidence["proposal_id"],
                            evidence["revision_id"],
                            regression_test_id,
                            evidence["skill_name"],
                            evidence["base_skill_version"],
                            new_version,
                            evidence["change_scope"],
                            evidence["base_instructions_snapshot"],
                            promoted_instructions,
                            reason,
                            actor,
                        ),
                    )
                    result_row = cur.fetchone()

                    cur.execute(
                        """
                        UPDATE service_skill_improvement_proposals
                        SET status = 'promoted'
                        WHERE id = %s
                        """,
                        (evidence["proposal_id"],),
                    )

                    record_event_in_transaction(
                        cur,
                        request_id=request_id,
                        event_type="skill_promotion_applied",
                        actor=actor,
                        details={
                            "promotion_id": str(promotion_id),
                            "proposal_id": str(
                                evidence["proposal_id"]
                            ),
                            "revision_id": (
                                str(evidence["revision_id"])
                                if evidence["revision_id"] is not None
                                else None
                            ),
                            "regression_test_id": str(
                                regression_test_id
                            ),
                            "skill_name": evidence["skill_name"],
                            "base_skill_version": evidence[
                                "base_skill_version"
                            ],
                            "promoted_skill_version": new_version,
                            "change_scope": evidence["change_scope"],
                            "human_authorized": True,
                            "regression_gate_passed": True,
                            "promotion_applied": True,
                            "skill_version_changed": True,
                            "registry_changed": True,
                            "production_behaviour_changed": True,
                        },
                    )

        _activate_promotion(result_row, registry)
        return _row_result(result_row)
