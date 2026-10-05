import unittest
from uuid import UUID

import skill_improvement as improvement


class SkillImprovementTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(
            improvement.SkillImprovementValidationError
        ):
            improvement.create_skill_improvement_proposal(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                change_scope="instructions",
                proposed_change="Draft change",
                rationale="Real-case evaluation identified a gap",
                actor="model:improver",
            )

    def test_rejects_unknown_scope(self):
        with self.assertRaises(
            improvement.SkillImprovementValidationError
        ):
            improvement.create_skill_improvement_proposal(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                change_scope="runtime",
                proposed_change="Draft change",
                rationale="Real-case evaluation identified a gap",
                actor="operator:test",
            )


if __name__ == "__main__":
    unittest.main()
