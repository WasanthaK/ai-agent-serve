import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import training_workspace as workspace


class TrainingWorkspaceTests(unittest.TestCase):
    def row(self, *, verdict, proposal=False, regression=None):
        now = datetime(2026, 10, 5, tzinfo=timezone.utc)
        row = {
            "evaluation_id": UUID("11111111-1111-1111-1111-111111111111"),
            "request_id": UUID("22222222-2222-2222-2222-222222222222"),
            "analysis_event_id": UUID("33333333-3333-3333-3333-333333333333"),
            "skill_name": "request_clarification",
            "skill_version": "1.0.0",
            "evaluation_verdict": verdict,
            "evaluation_notes": "Reviewed real case",
            "outcome_snapshot": {"satisfaction_rating": 3},
            "evaluated_by": "operator:test",
            "evaluation_created_at": now,
            "request_source": "website",
            "request_status": "actioned",
            "request_category": "plumbing",
            "request_summary": "Tap replacement",
            "request_urgency": "normal",
            "proposal_id": None,
            "change_scope": None,
            "proposed_change": None,
            "proposal_rationale": None,
            "proposal_status": None,
            "proposal_created_at": None,
            "revision_id": None,
            "revision_number": None,
            "revision_proposed_change": None,
            "revision_rationale": None,
            "revision_created_at": None,
            "regression_test_id": None,
            "regression_revision_id": None,
            "suite_name": None,
            "suite_version": None,
            "total_cases": None,
            "target_cases": None,
            "fixed_target_cases": None,
            "regression_failures": None,
            "candidate_failures": None,
            "regression_verdict": None,
            "regression_created_at": None,
            "promotion_id": None,
            "promoted_skill_version": None,
            "promotion_reason": None,
            "promoted_by": None,
            "promotion_created_at": None,
            "training_stage": None,
        }
        if proposal:
            row.update(
                proposal_id=UUID("44444444-4444-4444-4444-444444444444"),
                change_scope="instructions",
                proposed_change="Improve clarification logic",
                proposal_rationale="Real case exposed a gap",
                proposal_status="proposed",
                proposal_created_at=now,
            )
        if regression is not None:
            row.update(
                regression_test_id=UUID(
                    "55555555-5555-5555-5555-555555555555"
                ),
                suite_name="core",
                suite_version="1.0.0",
                total_cases=2,
                target_cases=1,
                fixed_target_cases=1 if regression == "pass" else 0,
                regression_failures=0 if regression == "pass" else 1,
                candidate_failures=0 if regression == "pass" else 1,
                regression_verdict=regression,
                regression_created_at=now,
            )
        return row

    def test_supported_actions_match_backend_capabilities(self):
        self.assertEqual(
            workspace._supported_actions("needs_improvement_proposal"),
            ["create_improvement_proposal"],
        )
        self.assertEqual(
            workspace._supported_actions("needs_regression_test"),
            ["record_regression_test"],
        )
        self.assertEqual(
            workspace._supported_actions("regression_failed"),
            ["create_improvement_revision"],
        )
        self.assertEqual(
            workspace._supported_actions("ready_for_promotion_review"),
            ["promote_skill"],
        )

    def test_blocked_states_are_explicit(self):
        self.assertIsNone(
            workspace._blocked_reason("regression_failed")
        )
        self.assertIsNone(
            workspace._blocked_reason("ready_for_promotion_review")
        )

    def test_result_exposes_human_promotion_action_only_after_pass(self):
        row = self.row(
            verdict="needs_review",
            proposal=True,
            regression="pass",
        )
        row["training_stage"] = "ready_for_promotion_review"

        result = workspace._result(row)

        self.assertEqual(
            result["training_stage"],
            "ready_for_promotion_review",
        )
        self.assertTrue(result["promotion_supported"])
        self.assertFalse(result["production_behaviour_changed"])
        self.assertEqual(
            result["supported_actions"],
            ["promote_skill"],
        )
        self.assertIsNone(result["blocked_reason"])

    def test_list_training_cases_scopes_query_to_tenant(self):
        tenant_id = uuid4()
        connection = MagicMock()
        cursor = (
            connection.__enter__.return_value
            .cursor.return_value.__enter__.return_value
        )
        cursor.fetchall.return_value = []

        with patch.object(
            workspace,
            "get_connection",
            return_value=connection,
        ):
            result = workspace.list_training_cases(
                tenant_id=tenant_id,
            )

        self.assertEqual(result, [])
        sql, params = cursor.execute.call_args.args
        self.assertIn("request_tenant_id = %s", sql)
        self.assertEqual(params, (tenant_id, 50))

    def test_list_training_cases_legacy_scope_excludes_tenant_rows(self):
        connection = MagicMock()
        cursor = (
            connection.__enter__.return_value
            .cursor.return_value.__enter__.return_value
        )
        cursor.fetchall.return_value = []

        with patch.object(
            workspace,
            "get_connection",
            return_value=connection,
        ):
            workspace.list_training_cases(tenant_id=None)

        sql, params = cursor.execute.call_args.args
        self.assertIn("request_tenant_id IS NULL", sql)
        self.assertEqual(params, (50,))

    def test_rejects_unknown_stage_and_invalid_limit(self):
        with self.assertRaises(
            workspace.TrainingWorkspaceValidationError
        ):
            workspace._normalize_stage("auto_promote")
        with self.assertRaises(
            workspace.TrainingWorkspaceValidationError
        ):
            workspace._normalize_limit(0)
        with self.assertRaises(
            workspace.TrainingWorkspaceValidationError
        ):
            workspace._normalize_limit(201)


if __name__ == "__main__":
    unittest.main()
