import unittest
from uuid import UUID

import skill_regression as regression


class SkillRegressionTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(
            regression.SkillRegressionValidationError
        ):
            regression.record_skill_regression_test(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                suite_name="core",
                suite_version="1.0.0",
                cases=[
                    {
                        "case_id": "target-1",
                        "purpose": "target",
                        "baseline_result": "fail",
                        "candidate_result": "pass",
                        "notes": "Fixed.",
                    },
                    {
                        "case_id": "regression-1",
                        "purpose": "regression",
                        "baseline_result": "pass",
                        "candidate_result": "pass",
                        "notes": "Preserved.",
                    },
                ],
                actor="model:judge",
            )

    def test_requires_target_and_regression_cases(self):
        with self.assertRaises(
            regression.SkillRegressionValidationError
        ):
            regression._normalize_cases(
                [
                    {
                        "case_id": "target-1",
                        "purpose": "target",
                        "baseline_result": "fail",
                        "candidate_result": "pass",
                        "notes": "Fixed.",
                    },
                    {
                        "case_id": "target-2",
                        "purpose": "target",
                        "baseline_result": "fail",
                        "candidate_result": "pass",
                        "notes": "Also fixed.",
                    },
                ]
            )

    def test_target_case_must_be_known_baseline_failure(self):
        with self.assertRaises(
            regression.SkillRegressionValidationError
        ):
            regression._normalize_cases(
                [
                    {
                        "case_id": "target-1",
                        "purpose": "target",
                        "baseline_result": "pass",
                        "candidate_result": "pass",
                        "notes": "Invalid target baseline.",
                    },
                    {
                        "case_id": "regression-1",
                        "purpose": "regression",
                        "baseline_result": "pass",
                        "candidate_result": "pass",
                        "notes": "Preserved.",
                    },
                ]
            )

    def test_gate_passes_only_when_target_fixed_and_regressions_preserved(self):
        passing = regression._normalize_cases(
            [
                {
                    "case_id": "target-1",
                    "purpose": "target",
                    "baseline_result": "fail",
                    "candidate_result": "pass",
                    "notes": "Fixed.",
                },
                {
                    "case_id": "regression-1",
                    "purpose": "regression",
                    "baseline_result": "pass",
                    "candidate_result": "pass",
                    "notes": "Preserved.",
                },
            ]
        )
        self.assertEqual(
            regression._summarize_cases(passing)["verdict"],
            "pass",
        )

        regressed = regression._normalize_cases(
            [
                {
                    "case_id": "target-1",
                    "purpose": "target",
                    "baseline_result": "fail",
                    "candidate_result": "pass",
                    "notes": "Fixed.",
                },
                {
                    "case_id": "regression-1",
                    "purpose": "regression",
                    "baseline_result": "pass",
                    "candidate_result": "fail",
                    "notes": "Candidate broke known-good behavior.",
                },
            ]
        )
        summary = regression._summarize_cases(regressed)
        self.assertEqual(summary["verdict"], "fail")
        self.assertEqual(summary["regression_failures"], 1)


if __name__ == "__main__":
    unittest.main()
