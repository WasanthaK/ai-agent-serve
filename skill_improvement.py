"""Controlled skill-instruction/policy improvement proposals.

Proposals are human-authored drafts tied to a real-case skill evaluation.
They never modify the live registry, instructions, policies, skill version, or
production behaviour. Application of a proposal is intentionally unsupported.
"""

import uuid

from psycopg.rows import dict_row

from agent_skills import skill_registry
from db import get_connection, record_event_in_transaction


ALLOWED_SCOPES = frozenset({"instructions", "policy"})
ELIGIBLE_EVALUATION_VERDICTS = frozenset({"needs_review", "fail"})


class SkillImprovementValidationError(ValueError):
    pass


class SkillImprovementNotFoundError(LookupError):
    pass


class SkillImprovementStateError(RuntimeError):
    pass


class SkillImprovementConflictError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise SkillImprovementValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise SkillImprovementValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise SkillImprovementValidationError("actor is required")
    if len(actor) > 200:
        raise SkillImprovementValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise SkillImprovementValidationError(
            "Improvement proposal authority must be an operator"
        )
    return actor


def _normalize_scope(change_scope):
    if not isinstance(change_scope, str):
        raise SkillImprovementValidationError(
            "change_scope must be text"
        )
    change_scope = change_scope.strip().lower()
    if change_scope not in ALLOWED_SCOPES:
        raise SkillImprovementValidationError(
            "change_scope must be instructions or policy"
        )
    return change_scope


def _normalize_text(value, field_name, max_length):
    if not isinstance(value, str):
        raise SkillImprovementValidationError(
            f"{field_name} must be text"
        )
    value = value.strip()
    if not value:
        raise SkillImprovementValidationError(
            f"{field_name} is required"
        )
    if len(value) > max_length:
        raise SkillImprovementValidationError(
            f"{field_name} is too long"
        )
    return value


def _result(row):
    promoted = row["status"] == "promoted"
    return {
        "proposal_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "evaluation_id": str(row["evaluation_id"]),
        "skill_name": row["skill_name"],
        "base_skill_version": row["base_skill_version"],
        "change_scope": row["change_scope"],
        "base_instructions_snapshot": row["base_instructions_snapshot"],
        "proposed_change": row["proposed_change"],
        "rationale": row["rationale"],
        "status": row["status"],
        "proposed_by": row["proposed_by"],
        "created_at": row["created_at"],
        "applied": promoted,
        "skill_version_changed": promoted,
        "registry_changed": promoted,
        "policy_change_applied": (
            promoted and row["change_scope"] == "policy"
        ),
        "production_behaviour_changed": promoted,
    }


def get_skill_improvement_proposals(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_skill_improvement_proposals
                WHERE request_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (request_id,),
            )
            return [_result(row) for row in cur.fetchall()]


def create_skill_improvement_proposal(
    request_id,
    evaluation_id,
    *,
    change_scope,
    proposed_change,
    rationale,
    actor,
):
    request_id = _validate_uuid(request_id, "request_id")
    evaluation_id = _validate_uuid(evaluation_id, "evaluation_id")
    change_scope = _normalize_scope(change_scope)
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
                FROM service_skill_evaluations
                WHERE request_id = %s
                  AND id = %s
                FOR UPDATE
                """,
                (request_id, evaluation_id),
            )
            evaluation = cur.fetchone()
            if evaluation is None:
                raise SkillImprovementNotFoundError(
                    "Skill evaluation not found for request"
                )
            if evaluation["verdict"] not in ELIGIBLE_EVALUATION_VERDICTS:
                raise SkillImprovementStateError(
                    "Improvement proposal requires needs_review or fail evaluation"
                )

            skill_name = evaluation["skill_name"]
            evaluated_version = evaluation["skill_version"]

            try:
                current_skill = skill_registry.get(skill_name)
            except KeyError as exc:
                raise SkillImprovementStateError(
                    "Evaluated skill is not currently registered"
                ) from exc

            if current_skill.version != evaluated_version:
                raise SkillImprovementStateError(
                    "Current registered skill version differs from evaluated version"
                )

            base_instructions = current_skill.instructions.strip()
            if not base_instructions:
                raise SkillImprovementStateError(
                    "Current registered skill has no instructions to snapshot"
                )

            cur.execute(
                """
                SELECT *
                FROM service_skill_improvement_proposals
                WHERE evaluation_id = %s
                FOR UPDATE
                """,
                (evaluation_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                same = (
                    existing["skill_name"] == skill_name
                    and existing["base_skill_version"]
                    == evaluated_version
                    and existing["change_scope"] == change_scope
                    and existing["base_instructions_snapshot"]
                    == base_instructions
                    and existing["proposed_change"] == proposed_change
                    and existing["rationale"] == rationale
                    and existing["proposed_by"] == actor
                )
                if same:
                    return _result(existing)
                raise SkillImprovementConflictError(
                    "A different improvement proposal already exists for evaluation"
                )

            proposal_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO service_skill_improvement_proposals (
                    id,
                    request_id,
                    evaluation_id,
                    skill_name,
                    base_skill_version,
                    change_scope,
                    base_instructions_snapshot,
                    proposed_change,
                    rationale,
                    proposed_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    proposal_id,
                    request_id,
                    evaluation_id,
                    skill_name,
                    evaluated_version,
                    change_scope,
                    base_instructions,
                    proposed_change,
                    rationale,
                    actor,
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="skill_improvement_proposal_created",
                actor=actor,
                details={
                    "proposal_id": str(proposal_id),
                    "evaluation_id": str(evaluation_id),
                    "skill_name": skill_name,
                    "base_skill_version": evaluated_version,
                    "change_scope": change_scope,
                    "applied": False,
                    "skill_version_changed": False,
                    "registry_changed": False,
                    "policy_change_applied": False,
                    "production_behaviour_changed": False,
                },
            )

            return _result(created)
