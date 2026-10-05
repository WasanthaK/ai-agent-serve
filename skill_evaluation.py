"""Human-reviewed skill evaluation against persisted real cases.

Evaluations are bound to the exact analysis event and historical skill version
that actually ran. Outcome evidence is snapshotted for review only. Nothing in
this module changes prompts, policies, skill versions, rankings, or production
behaviour.
"""

from datetime import date, datetime
import uuid

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from db import get_connection, record_event_in_transaction
from outcome_measurement import (
    OutcomeMeasurementNotFoundError,
    get_outcome_measurement,
)


ALLOWED_VERDICTS = frozenset({"pass", "needs_review", "fail"})
ANALYSIS_EVENT_TYPES = frozenset({"request_created", "request_reanalysed"})


class SkillEvaluationValidationError(ValueError):
    pass


class SkillEvaluationNotFoundError(LookupError):
    pass


class SkillEvaluationStateError(RuntimeError):
    pass


class SkillEvaluationConflictError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise SkillEvaluationValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise SkillEvaluationValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise SkillEvaluationValidationError("actor is required")
    if len(actor) > 200:
        raise SkillEvaluationValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise SkillEvaluationValidationError(
            "Skill evaluation authority must be an operator"
        )
    return actor


def _normalize_skill_name(skill_name):
    if not isinstance(skill_name, str):
        raise SkillEvaluationValidationError("skill_name must be text")
    skill_name = skill_name.strip()
    if not skill_name:
        raise SkillEvaluationValidationError("skill_name is required")
    if len(skill_name) > 120:
        raise SkillEvaluationValidationError("skill_name is too long")
    return skill_name


def _normalize_verdict(verdict):
    if not isinstance(verdict, str):
        raise SkillEvaluationValidationError("verdict must be text")
    verdict = verdict.strip().lower()
    if verdict not in ALLOWED_VERDICTS:
        raise SkillEvaluationValidationError(
            "verdict must be pass, needs_review, or fail"
        )
    return verdict


def _normalize_notes(notes):
    if not isinstance(notes, str):
        raise SkillEvaluationValidationError("notes must be text")
    notes = notes.strip()
    if not notes:
        raise SkillEvaluationValidationError("notes are required")
    if len(notes) > 4000:
        raise SkillEvaluationValidationError("notes are too long")
    return notes


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _result(row):
    return {
        "evaluation_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "analysis_event_id": str(row["analysis_event_id"]),
        "skill_name": row["skill_name"],
        "skill_version": row["skill_version"],
        "verdict": row["verdict"],
        "notes": row["notes"],
        "outcome_snapshot": dict(row["outcome_snapshot"]),
        "evaluated_by": row["evaluated_by"],
        "created_at": row["created_at"],
        "training_signal_applied": False,
        "skill_version_changed": False,
        "policy_change_applied": False,
        "promotion_applied": False,
        "production_behaviour_changed": False,
    }


def get_skill_evaluations(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_skill_evaluations
                WHERE request_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (request_id,),
            )
            return [_result(row) for row in cur.fetchall()]


def create_skill_evaluation(
    request_id,
    analysis_event_id,
    skill_name,
    *,
    verdict,
    notes,
    actor,
):
    request_id = _validate_uuid(request_id, "request_id")
    analysis_event_id = _validate_uuid(
        analysis_event_id,
        "analysis_event_id",
    )
    skill_name = _normalize_skill_name(skill_name)
    verdict = _normalize_verdict(verdict)
    notes = _normalize_notes(notes)
    actor = _normalize_actor(actor)

    try:
        outcome_snapshot = _json_safe(
            get_outcome_measurement(request_id)
        )
    except OutcomeMeasurementNotFoundError as exc:
        raise SkillEvaluationNotFoundError("Request not found") from exc

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
                raise SkillEvaluationNotFoundError("Request not found")

            cur.execute(
                """
                SELECT id, request_id, event_type, details
                FROM agent_events
                WHERE request_id = %s
                  AND id = %s
                FOR UPDATE
                """,
                (request_id, analysis_event_id),
            )
            event = cur.fetchone()
            if event is None:
                raise SkillEvaluationNotFoundError(
                    "Analysis event not found for request"
                )
            if event["event_type"] not in ANALYSIS_EVENT_TYPES:
                raise SkillEvaluationStateError(
                    "Skill evaluation requires request_created or request_reanalysed event"
                )

            details = dict(event["details"] or {})
            versions = details.get("skill_versions")
            if not isinstance(versions, dict):
                raise SkillEvaluationStateError(
                    "Analysis event does not contain skill-version provenance"
                )

            skill_version = versions.get(skill_name)
            if not isinstance(skill_version, str) or not skill_version.strip():
                raise SkillEvaluationStateError(
                    "Skill was not recorded on the selected analysis event"
                )
            skill_version = skill_version.strip()

            cur.execute(
                """
                SELECT *
                FROM service_skill_evaluations
                WHERE analysis_event_id = %s
                  AND skill_name = %s
                FOR UPDATE
                """,
                (analysis_event_id, skill_name),
            )
            existing = cur.fetchone()
            if existing is not None:
                same = (
                    existing["skill_version"] == skill_version
                    and existing["verdict"] == verdict
                    and existing["notes"] == notes
                    and existing["evaluated_by"] == actor
                )
                if same:
                    return _result(existing)
                raise SkillEvaluationConflictError(
                    "A different evaluation already exists for this skill and analysis event"
                )

            evaluation_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO service_skill_evaluations (
                    id,
                    request_id,
                    analysis_event_id,
                    skill_name,
                    skill_version,
                    verdict,
                    notes,
                    outcome_snapshot,
                    evaluated_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    evaluation_id,
                    request_id,
                    analysis_event_id,
                    skill_name,
                    skill_version,
                    verdict,
                    notes,
                    Jsonb(outcome_snapshot),
                    actor,
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="skill_real_case_evaluation_recorded",
                actor=actor,
                details={
                    "evaluation_id": str(evaluation_id),
                    "analysis_event_id": str(analysis_event_id),
                    "skill_name": skill_name,
                    "skill_version": skill_version,
                    "verdict": verdict,
                    "training_signal_applied": False,
                    "skill_version_changed": False,
                    "policy_change_applied": False,
                    "promotion_applied": False,
                    "production_behaviour_changed": False,
                },
            )

            return _result(created)
