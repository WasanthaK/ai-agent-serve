"""Immutable human-authored revisions after failed skill regression.

A failed regression does not permit mutation of the original improvement
proposal. Instead, an operator may create a numbered revision that explicitly
supersedes the failed regression evidence. Revisions remain unapplied and do
not change live skill instructions, registry state, versions, or production
behaviour.
"""

import uuid

from psycopg.rows import dict_row

from agent_skills import skill_registry
from db import get_connection, record_event_in_transaction


class SkillRevisionValidationError(ValueError):
    pass


class SkillRevisionNotFoundError(LookupError):
    pass


class SkillRevisionStateError(RuntimeError):
    pass


class SkillRevisionConflictError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise SkillRevisionValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise SkillRevisionValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise SkillRevisionValidationError("actor is required")
    if len(actor) > 200:
        raise SkillRevisionValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise SkillRevisionValidationError(
            "Skill revision authority must be an operator"
        )
    return actor


def _normalize_text(value, field_name, max_length):
    if not isinstance(value, str):
        raise SkillRevisionValidationError(
            f"{field_name} must be text"
        )
    value = value.strip()
    if not value:
        raise SkillRevisionValidationError(
            f"{field_name} is required"
        )
    if len(value) > max_length:
        raise SkillRevisionValidationError(
            f"{field_name} is too long"
        )
    return value


def _result(row):
    return {
        "revision_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "proposal_id": str(row["proposal_id"]),
        "revision_number": row["revision_number"],
        "supersedes_regression_test_id": str(
            row["supersedes_regression_test_id"]
        ),
        "proposed_change": row["proposed_change"],
        "rationale": row["rationale"],
        "revised_by": row["revised_by"],
        "created_at": row["created_at"],
        "applied": False,
        "skill_version_changed": False,
        "registry_changed": False,
        "promotion_applied": False,
        "production_behaviour_changed": False,
    }


def get_skill_improvement_revisions(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_skill_improvement_revisions
                WHERE request_id = %s
                ORDER BY revision_number ASC, created_at ASC, id ASC
                """,
                (request_id,),
            )
            return [_result(row) for row in cur.fetchall()]


def create_skill_improvement_revision(
    request_id,
    proposal_id,
    *,
    proposed_change,
    rationale,
    actor,
):
    request_id = _validate_uuid(request_id, "request_id")
    proposal_id = _validate_uuid(proposal_id, "proposal_id")
    proposed_change = _normalize_text(
        proposed_change,
        "proposed_change",
        12000,
    )
    rationale = _normalize_text(rationale, "rationale", 4000)
    actor = _normalize_actor(actor)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_skill_improvement_proposals
                WHERE request_id = %s
                  AND id = %s
                FOR UPDATE
                """,
                (request_id, proposal_id),
            )
            proposal = cur.fetchone()
            if proposal is None:
                raise SkillRevisionNotFoundError(
                    "Skill improvement proposal not found for request"
                )
            if proposal["status"] != "proposed":
                raise SkillRevisionStateError(
                    "Revision requires a proposed improvement"
                )

            try:
                current_skill = skill_registry.get(
                    proposal["skill_name"]
                )
            except KeyError as exc:
                raise SkillRevisionStateError(
                    "Proposed skill is not currently registered"
                ) from exc

            if current_skill.version != proposal["base_skill_version"]:
                raise SkillRevisionStateError(
                    "Current registered skill version differs from proposal base version"
                )
            if (
                current_skill.instructions.strip()
                != proposal["base_instructions_snapshot"]
            ):
                raise SkillRevisionStateError(
                    "Current registered skill instructions differ from proposal base snapshot"
                )

            cur.execute(
                """
                SELECT *
                FROM service_skill_improvement_revisions
                WHERE proposal_id = %s
                ORDER BY revision_number DESC
                LIMIT 1
                FOR UPDATE
                """,
                (proposal_id,),
            )
            latest_revision = cur.fetchone()

            if latest_revision is None:
                cur.execute(
                    """
                    SELECT *
                    FROM service_skill_regression_tests
                    WHERE proposal_id = %s
                      AND revision_id IS NULL
                    FOR UPDATE
                    """,
                    (proposal_id,),
                )
                predecessor_test = cur.fetchone()
                next_number = 1
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM service_skill_regression_tests
                    WHERE revision_id = %s
                    FOR UPDATE
                    """,
                    (latest_revision["id"],),
                )
                predecessor_test = cur.fetchone()
                if predecessor_test is None:
                    same = (
                        latest_revision["proposed_change"]
                        == proposed_change
                        and latest_revision["rationale"] == rationale
                        and latest_revision["revised_by"] == actor
                    )
                    if same:
                        return _result(latest_revision)
                    raise SkillRevisionConflictError(
                        "Latest revision is awaiting regression evidence"
                    )
                next_number = latest_revision["revision_number"] + 1

            if predecessor_test is None:
                raise SkillRevisionStateError(
                    "Revision requires failed regression evidence"
                )
            if predecessor_test["verdict"] != "fail":
                raise SkillRevisionStateError(
                    "Only failed regression evidence can be revised"
                )

            cur.execute(
                """
                SELECT *
                FROM service_skill_improvement_revisions
                WHERE supersedes_regression_test_id = %s
                FOR UPDATE
                """,
                (predecessor_test["id"],),
            )
            existing = cur.fetchone()
            if existing is not None:
                same = (
                    existing["proposal_id"] == proposal_id
                    and existing["proposed_change"] == proposed_change
                    and existing["rationale"] == rationale
                    and existing["revised_by"] == actor
                )
                if same:
                    return _result(existing)
                raise SkillRevisionConflictError(
                    "A different revision already supersedes this failed regression"
                )

            revision_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO service_skill_improvement_revisions (
                    id,
                    request_id,
                    proposal_id,
                    revision_number,
                    supersedes_regression_test_id,
                    proposed_change,
                    rationale,
                    revised_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    revision_id,
                    request_id,
                    proposal_id,
                    next_number,
                    predecessor_test["id"],
                    proposed_change,
                    rationale,
                    actor,
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="skill_improvement_revision_created",
                actor=actor,
                details={
                    "revision_id": str(revision_id),
                    "proposal_id": str(proposal_id),
                    "revision_number": next_number,
                    "supersedes_regression_test_id": str(
                        predecessor_test["id"]
                    ),
                    "skill_name": proposal["skill_name"],
                    "base_skill_version": proposal["base_skill_version"],
                    "applied": False,
                    "skill_version_changed": False,
                    "registry_changed": False,
                    "promotion_applied": False,
                    "production_behaviour_changed": False,
                },
            )

            return _result(created)
