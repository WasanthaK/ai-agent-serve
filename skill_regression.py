"""Human-reviewed regression evidence for skill improvement proposals.

This module records whether a proposed skill change fixed known target failures
without breaking known-good regression cases. It is a gate only: it does not
apply the proposal, mutate the registry, increment a skill version, or change
production behaviour.
"""

import uuid

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from agent_skills import skill_registry
from db import get_connection, record_event_in_transaction


CASE_PURPOSES = frozenset({"target", "regression"})
CASE_RESULTS = frozenset({"pass", "fail"})
MAX_CASES = 100


class SkillRegressionValidationError(ValueError):
    pass


class SkillRegressionNotFoundError(LookupError):
    pass


class SkillRegressionStateError(RuntimeError):
    pass


class SkillRegressionConflictError(RuntimeError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise SkillRegressionValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _normalize_actor(actor):
    if not isinstance(actor, str):
        raise SkillRegressionValidationError("actor must be text")
    actor = actor.strip()
    if not actor:
        raise SkillRegressionValidationError("actor is required")
    if len(actor) > 200:
        raise SkillRegressionValidationError("actor is too long")
    if not actor.startswith("operator:"):
        raise SkillRegressionValidationError(
            "Skill regression authority must be an operator"
        )
    return actor


def _normalize_text(value, field_name, max_length):
    if not isinstance(value, str):
        raise SkillRegressionValidationError(
            f"{field_name} must be text"
        )
    value = value.strip()
    if not value:
        raise SkillRegressionValidationError(
            f"{field_name} is required"
        )
    if len(value) > max_length:
        raise SkillRegressionValidationError(
            f"{field_name} is too long"
        )
    return value


def _normalize_case_result(value, field_name):
    if not isinstance(value, str):
        raise SkillRegressionValidationError(
            f"{field_name} must be text"
        )
    value = value.strip().lower()
    if value not in CASE_RESULTS:
        raise SkillRegressionValidationError(
            f"{field_name} must be pass or fail"
        )
    return value


def _normalize_cases(cases):
    if not isinstance(cases, list):
        raise SkillRegressionValidationError("cases must be a list")
    if len(cases) < 2:
        raise SkillRegressionValidationError(
            "Regression evidence requires at least one target case and one regression case"
        )
    if len(cases) > MAX_CASES:
        raise SkillRegressionValidationError(
            f"Regression evidence supports at most {MAX_CASES} cases"
        )

    normalized = []
    seen_case_ids = set()
    target_count = 0
    regression_count = 0

    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise SkillRegressionValidationError(
                f"cases[{index}] must be an object"
            )

        case_id = _normalize_text(
            case.get("case_id"),
            f"cases[{index}].case_id",
            120,
        )
        if case_id in seen_case_ids:
            raise SkillRegressionValidationError(
                f"Duplicate regression case_id: {case_id}"
            )
        seen_case_ids.add(case_id)

        purpose = _normalize_text(
            case.get("purpose"),
            f"cases[{index}].purpose",
            20,
        ).lower()
        if purpose not in CASE_PURPOSES:
            raise SkillRegressionValidationError(
                f"cases[{index}].purpose must be target or regression"
            )

        baseline_result = _normalize_case_result(
            case.get("baseline_result"),
            f"cases[{index}].baseline_result",
        )
        candidate_result = _normalize_case_result(
            case.get("candidate_result"),
            f"cases[{index}].candidate_result",
        )
        notes = _normalize_text(
            case.get("notes"),
            f"cases[{index}].notes",
            2000,
        )

        if purpose == "target":
            target_count += 1
            if baseline_result != "fail":
                raise SkillRegressionValidationError(
                    "Target cases must represent a known baseline failure"
                )
        else:
            regression_count += 1
            if baseline_result != "pass":
                raise SkillRegressionValidationError(
                    "Regression cases must represent known-good baseline behaviour"
                )

        normalized.append(
            {
                "case_id": case_id,
                "purpose": purpose,
                "baseline_result": baseline_result,
                "candidate_result": candidate_result,
                "notes": notes,
            }
        )

    if target_count == 0 or regression_count == 0:
        raise SkillRegressionValidationError(
            "Regression evidence requires at least one target case and one regression case"
        )

    return normalized


def _summarize_cases(cases):
    target_cases = sum(
        1 for case in cases if case["purpose"] == "target"
    )
    fixed_target_cases = sum(
        1
        for case in cases
        if case["purpose"] == "target"
        and case["candidate_result"] == "pass"
    )
    regression_failures = sum(
        1
        for case in cases
        if case["purpose"] == "regression"
        and case["candidate_result"] == "fail"
    )
    candidate_failures = sum(
        1 for case in cases if case["candidate_result"] == "fail"
    )

    verdict = (
        "pass"
        if fixed_target_cases == target_cases
        and regression_failures == 0
        and candidate_failures == 0
        else "fail"
    )

    return {
        "total_cases": len(cases),
        "target_cases": target_cases,
        "fixed_target_cases": fixed_target_cases,
        "regression_failures": regression_failures,
        "candidate_failures": candidate_failures,
        "verdict": verdict,
    }


def _result(row):
    verdict = row["verdict"]
    return {
        "regression_test_id": str(row["id"]),
        "request_id": str(row["request_id"]),
        "proposal_id": str(row["proposal_id"]),
        "revision_id": (
            str(row["revision_id"])
            if row.get("revision_id") is not None
            else None
        ),
        "skill_name": row["skill_name"],
        "base_skill_version": row["base_skill_version"],
        "change_scope": row["change_scope"],
        "suite_name": row["suite_name"],
        "suite_version": row["suite_version"],
        "cases": list(row["case_results"]),
        "total_cases": row["total_cases"],
        "target_cases": row["target_cases"],
        "fixed_target_cases": row["fixed_target_cases"],
        "regression_failures": row["regression_failures"],
        "candidate_failures": row["candidate_failures"],
        "verdict": verdict,
        "regression_gate_passed": verdict == "pass",
        "tested_by": row["tested_by"],
        "created_at": row["created_at"],
        "proposal_applied": False,
        "skill_version_changed": False,
        "registry_changed": False,
        "promotion_applied": False,
        "production_behaviour_changed": False,
    }


def get_skill_regression_tests(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM service_skill_regression_tests
                WHERE request_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (request_id,),
            )
            return [_result(row) for row in cur.fetchall()]


def record_skill_regression_test(
    request_id,
    proposal_id,
    *,
    revision_id=None,
    suite_name,
    suite_version,
    cases,
    actor,
):
    request_id = _validate_uuid(request_id, "request_id")
    proposal_id = _validate_uuid(proposal_id, "proposal_id")
    if revision_id is not None:
        revision_id = _validate_uuid(revision_id, "revision_id")
    suite_name = _normalize_text(suite_name, "suite_name", 120)
    suite_version = _normalize_text(
        suite_version,
        "suite_version",
        120,
    )
    normalized_cases = _normalize_cases(cases)
    summary = _summarize_cases(normalized_cases)
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
                raise SkillRegressionNotFoundError(
                    "Skill improvement proposal not found for request"
                )
            if proposal["status"] != "proposed":
                raise SkillRegressionStateError(
                    "Regression testing requires a proposed improvement"
                )

            skill_name = proposal["skill_name"]
            base_skill_version = proposal["base_skill_version"]

            revision = None
            if revision_id is not None:
                cur.execute(
                    """
                    SELECT *
                    FROM service_skill_improvement_revisions
                    WHERE request_id = %s
                      AND proposal_id = %s
                      AND id = %s
                    FOR UPDATE
                    """,
                    (request_id, proposal_id, revision_id),
                )
                revision = cur.fetchone()
                if revision is None:
                    raise SkillRegressionNotFoundError(
                        "Skill improvement revision not found for proposal"
                    )

                cur.execute(
                    """
                    SELECT id
                    FROM service_skill_improvement_revisions
                    WHERE proposal_id = %s
                      AND revision_number > %s
                    LIMIT 1
                    """,
                    (proposal_id, revision["revision_number"]),
                )
                if cur.fetchone() is not None:
                    raise SkillRegressionStateError(
                        "Regression testing must target the latest revision"
                    )

            try:
                current_skill = skill_registry.get(skill_name)
            except KeyError as exc:
                raise SkillRegressionStateError(
                    "Proposed skill is not currently registered"
                ) from exc

            if current_skill.version != base_skill_version:
                raise SkillRegressionStateError(
                    "Current registered skill version differs from proposal base version"
                )

            if (
                current_skill.instructions.strip()
                != proposal["base_instructions_snapshot"]
            ):
                raise SkillRegressionStateError(
                    "Current registered skill instructions differ from proposal base snapshot"
                )

            if revision_id is None:
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
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM service_skill_regression_tests
                    WHERE revision_id = %s
                    FOR UPDATE
                    """,
                    (revision_id,),
                )
            existing = cur.fetchone()
            if existing is not None:
                same = (
                    existing["request_id"] == request_id
                    and existing.get("revision_id") == revision_id
                    and existing["skill_name"] == skill_name
                    and existing["base_skill_version"]
                    == base_skill_version
                    and existing["change_scope"]
                    == proposal["change_scope"]
                    and existing["suite_name"] == suite_name
                    and existing["suite_version"] == suite_version
                    and list(existing["case_results"])
                    == normalized_cases
                    and existing["total_cases"]
                    == summary["total_cases"]
                    and existing["target_cases"]
                    == summary["target_cases"]
                    and existing["fixed_target_cases"]
                    == summary["fixed_target_cases"]
                    and existing["regression_failures"]
                    == summary["regression_failures"]
                    and existing["candidate_failures"]
                    == summary["candidate_failures"]
                    and existing["verdict"] == summary["verdict"]
                    and existing["tested_by"] == actor
                )
                if same:
                    return _result(existing)
                raise SkillRegressionConflictError(
                    "A different regression test already exists for proposal"
                )

            regression_test_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO service_skill_regression_tests (
                    id,
                    request_id,
                    proposal_id,
                    skill_name,
                    base_skill_version,
                    change_scope,
                    revision_id,
                    suite_name,
                    suite_version,
                    case_results,
                    total_cases,
                    target_cases,
                    fixed_target_cases,
                    regression_failures,
                    candidate_failures,
                    verdict,
                    tested_by
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING *
                """,
                (
                    regression_test_id,
                    request_id,
                    proposal_id,
                    skill_name,
                    base_skill_version,
                    proposal["change_scope"],
                    revision_id,
                    suite_name,
                    suite_version,
                    Jsonb(normalized_cases),
                    summary["total_cases"],
                    summary["target_cases"],
                    summary["fixed_target_cases"],
                    summary["regression_failures"],
                    summary["candidate_failures"],
                    summary["verdict"],
                    actor,
                ),
            )
            created = cur.fetchone()

            record_event_in_transaction(
                cur,
                request_id=request_id,
                event_type="skill_regression_test_recorded",
                actor=actor,
                details={
                    "regression_test_id": str(regression_test_id),
                    "proposal_id": str(proposal_id),
                    "revision_id": (
                        str(revision_id)
                        if revision_id is not None
                        else None
                    ),
                    "skill_name": skill_name,
                    "base_skill_version": base_skill_version,
                    "suite_name": suite_name,
                    "suite_version": suite_version,
                    "total_cases": summary["total_cases"],
                    "target_cases": summary["target_cases"],
                    "fixed_target_cases": summary["fixed_target_cases"],
                    "regression_failures": summary["regression_failures"],
                    "candidate_failures": summary["candidate_failures"],
                    "verdict": summary["verdict"],
                    "regression_gate_passed": (
                        summary["verdict"] == "pass"
                    ),
                    "proposal_applied": False,
                    "skill_version_changed": False,
                    "registry_changed": False,
                    "promotion_applied": False,
                    "production_behaviour_changed": False,
                },
            )

            return _result(created)
