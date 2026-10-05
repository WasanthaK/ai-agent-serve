import unittest
from uuid import UUID

import skill_evaluation as evaluation


class SkillEvaluationTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(
            evaluation.SkillEvaluationValidationError
        ):
            evaluation.create_skill_evaluation(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                "request_intake",
                verdict="pass",
                notes="Reviewed case",
                actor="model:evaluator",
            )

    def test_rejects_unknown_verdict(self):
        with self.assertRaises(
            evaluation.SkillEvaluationValidationError
        ):
            evaluation.create_skill_evaluation(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                "request_intake",
                verdict="promote",
                notes="Reviewed case",
                actor="operator:test",
            )


if __name__ == "__main__":
    unittest.main()
