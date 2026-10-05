"""Read-only training workspace projection for human skill improvement.

The training workspace consolidates real-case evaluation, improvement proposal,
and regression evidence into one UI-oriented queue. It exposes no new write,
promotion, registry, prompt, policy, or production authority.
"""

import uuid

from psycopg.rows import dict_row

from db import get_connection


TRAINING_STAGES = frozenset(
    {
        "accepted",
        "needs_improvement_proposal",
        "needs_regression_test",
        "regression_failed",
        "ready_for_promotion_review",
        "promoted",
    }
)
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
_UNSCOPED = object()


class TrainingWorkspaceValidationError(ValueError):
    pass


class TrainingWorkspaceNotFoundError(LookupError):
    pass


def _normalize_stage(stage):
    if stage is None:
        return None
    if not isinstance(stage, str):
        raise TrainingWorkspaceValidationError("stage must be text")
    stage = stage.strip().lower()
    if stage not in TRAINING_STAGES:
        raise TrainingWorkspaceValidationError(
            "Unknown training stage"
        )
    return stage


def _normalize_skill_name(skill_name):
    if skill_name is None:
        return None
    if not isinstance(skill_name, str):
        raise TrainingWorkspaceValidationError(
            "skill_name must be text"
        )
    skill_name = skill_name.strip()
    if not skill_name:
        raise TrainingWorkspaceValidationError(
            "skill_name cannot be empty"
        )
    if len(skill_name) > 120:
        raise TrainingWorkspaceValidationError(
            "skill_name is too long"
        )
    return skill_name


def _normalize_limit(limit):
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise TrainingWorkspaceValidationError(
            "limit must be an integer"
        )
    if limit < 1 or limit > MAX_LIMIT:
        raise TrainingWorkspaceValidationError(
            f"limit must be between 1 and {MAX_LIMIT}"
        )
    return limit


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise TrainingWorkspaceValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _supported_actions(stage):
    if stage == "needs_improvement_proposal":
        return ["create_improvement_proposal"]
    if stage == "needs_regression_test":
        return ["record_regression_test"]
    if stage == "regression_failed":
        return ["create_improvement_revision"]
    if stage == "ready_for_promotion_review":
        return ["promote_skill"]
    return []


def _blocked_reason(stage):
    return None


def _result(row):
    stage = row["training_stage"]
    return {
        "evaluation_id": str(row["evaluation_id"]),
        "request_id": str(row["request_id"]),
        "analysis_event_id": str(row["analysis_event_id"]),
        "skill_name": row["skill_name"],
        "skill_version": row["skill_version"],
        "evaluation_verdict": row["evaluation_verdict"],
        "evaluation_notes": row["evaluation_notes"],
        "outcome_snapshot": dict(row["outcome_snapshot"]),
        "evaluated_by": row["evaluated_by"],
        "evaluation_created_at": row["evaluation_created_at"],
        "request": {
            "source": row["request_source"],
            "status": row["request_status"],
            "category": row["request_category"],
            "summary": row["request_summary"],
            "urgency": row["request_urgency"],
        },
        "proposal": (
            None
            if row["proposal_id"] is None
            else {
                "proposal_id": str(row["proposal_id"]),
                "change_scope": row["change_scope"],
                "proposed_change": row["proposed_change"],
                "rationale": row["proposal_rationale"],
                "status": row["proposal_status"],
                "created_at": row["proposal_created_at"],
            }
        ),
        "revision": (
            None
            if row["revision_id"] is None
            else {
                "revision_id": str(row["revision_id"]),
                "revision_number": row["revision_number"],
                "proposed_change": row["revision_proposed_change"],
                "rationale": row["revision_rationale"],
                "created_at": row["revision_created_at"],
            }
        ),
        "promotion": (
            None
            if row["promotion_id"] is None
            else {
                "promotion_id": str(row["promotion_id"]),
                "promoted_skill_version": row["promoted_skill_version"],
                "reason": row["promotion_reason"],
                "promoted_by": row["promoted_by"],
                "created_at": row["promotion_created_at"],
            }
        ),
        "regression": (
            None
            if row["regression_test_id"] is None
            else {
                "regression_test_id": str(row["regression_test_id"]),
                "revision_id": (
                    str(row["regression_revision_id"])
                    if row["regression_revision_id"] is not None
                    else None
                ),
                "suite_name": row["suite_name"],
                "suite_version": row["suite_version"],
                "total_cases": row["total_cases"],
                "target_cases": row["target_cases"],
                "fixed_target_cases": row["fixed_target_cases"],
                "regression_failures": row["regression_failures"],
                "candidate_failures": row["candidate_failures"],
                "verdict": row["regression_verdict"],
                "created_at": row["regression_created_at"],
            }
        ),
        "training_stage": stage,
        "supported_actions": _supported_actions(stage),
        "blocked_reason": _blocked_reason(stage),
        "promotion_supported": stage == "ready_for_promotion_review",
        "production_behaviour_changed": stage == "promoted",
    }


_PROJECTION_SQL = """
    SELECT
        e.id AS evaluation_id,
        e.request_id,
        e.analysis_event_id,
        e.skill_name,
        e.skill_version,
        e.verdict AS evaluation_verdict,
        e.notes AS evaluation_notes,
        e.outcome_snapshot,
        e.evaluated_by,
        e.created_at AS evaluation_created_at,
        r.source AS request_source,
        r.status AS request_status,
        r.category AS request_category,
        r.summary AS request_summary,
        r.urgency AS request_urgency,
        r.tenant_id AS request_tenant_id,
        p.id AS proposal_id,
        p.change_scope,
        p.proposed_change,
        p.rationale AS proposal_rationale,
        p.status AS proposal_status,
        p.created_at AS proposal_created_at,
        rev.id AS revision_id,
        rev.revision_number,
        rev.proposed_change AS revision_proposed_change,
        rev.rationale AS revision_rationale,
        rev.created_at AS revision_created_at,
        t.id AS regression_test_id,
        t.revision_id AS regression_revision_id,
        t.suite_name,
        t.suite_version,
        t.total_cases,
        t.target_cases,
        t.fixed_target_cases,
        t.regression_failures,
        t.candidate_failures,
        t.verdict AS regression_verdict,
        t.created_at AS regression_created_at,
        pr.id AS promotion_id,
        pr.promoted_skill_version,
        pr.reason AS promotion_reason,
        pr.promoted_by,
        pr.created_at AS promotion_created_at,
        CASE
            WHEN pr.id IS NOT NULL
                THEN 'promoted'
            WHEN e.verdict = 'pass'
                THEN 'accepted'
            WHEN p.id IS NULL
                THEN 'needs_improvement_proposal'
            WHEN t.id IS NULL
                THEN 'needs_regression_test'
            WHEN t.verdict = 'fail'
                THEN 'regression_failed'
            WHEN t.verdict = 'pass'
                THEN 'ready_for_promotion_review'
        END AS training_stage
    FROM service_skill_evaluations e
    JOIN agent_requests r
      ON r.id = e.request_id
    LEFT JOIN service_skill_improvement_proposals p
      ON p.evaluation_id = e.id
    LEFT JOIN LATERAL (
        SELECT sr.*
        FROM service_skill_improvement_revisions sr
        WHERE sr.proposal_id = p.id
        ORDER BY sr.revision_number DESC
        LIMIT 1
    ) rev ON TRUE
    LEFT JOIN service_skill_regression_tests t
      ON (
          rev.id IS NOT NULL
          AND t.revision_id = rev.id
      )
      OR (
          rev.id IS NULL
          AND t.proposal_id = p.id
          AND t.revision_id IS NULL
      )
    LEFT JOIN service_skill_promotions pr
      ON pr.regression_test_id = t.id
"""


def list_training_cases(
    *,
    stage=None,
    skill_name=None,
    limit=DEFAULT_LIMIT,
    tenant_id=_UNSCOPED,
):
    stage = _normalize_stage(stage)
    skill_name = _normalize_skill_name(skill_name)
    limit = _normalize_limit(limit)

    filters = []
    params = []

    if tenant_id is None:
        filters.append("request_tenant_id IS NULL")
    elif tenant_id is not _UNSCOPED:
        _validate_uuid(tenant_id, "tenant_id")
        filters.append("request_tenant_id = %s")
        params.append(tenant_id)

    if stage is not None:
        filters.append("training_stage = %s")
        params.append(stage)
    if skill_name is not None:
        filters.append("skill_name = %s")
        params.append(skill_name)

    where_clause = ""
    if filters:
        where_clause = "WHERE " + " AND ".join(filters)

    query = f"""
        WITH training_cases AS (
            {_PROJECTION_SQL}
        )
        SELECT *
        FROM training_cases
        {where_clause}
        ORDER BY evaluation_created_at DESC, evaluation_id DESC
        LIMIT %s
    """
    params.append(limit)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, tuple(params))
            return [_result(row) for row in cur.fetchall()]


def get_training_case(evaluation_id, *, tenant_id=_UNSCOPED):
    evaluation_id = _validate_uuid(
        evaluation_id,
        "evaluation_id",
    )

    filters = ["evaluation_id = %s"]
    params = [evaluation_id]
    if tenant_id is None:
        filters.append("request_tenant_id IS NULL")
    elif tenant_id is not _UNSCOPED:
        _validate_uuid(tenant_id, "tenant_id")
        filters.append("request_tenant_id = %s")
        params.append(tenant_id)

    query = f"""
        WITH training_cases AS (
            {_PROJECTION_SQL}
        )
        SELECT *
        FROM training_cases
        WHERE {" AND ".join(filters)}
    """

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, tuple(params))
            row = cur.fetchone()
            if row is None:
                raise TrainingWorkspaceNotFoundError(
                    "Training case not found"
                )
            return _result(row)
