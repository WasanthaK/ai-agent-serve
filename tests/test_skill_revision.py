import unittest
from uuid import UUID

import skill_revision as revision


class SkillRevisionTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(
            revision.SkillRevisionValidationError
        ):
            revision.create_skill_improvement_revision(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                proposed_change="Revised change",
                rationale="Regression failed",
                actor="model:improver",
            )

    def test_rejects_empty_revision_text(self):
        with self.assertRaises(
            revision.SkillRevisionValidationError
        ):
            revision.create_skill_improvement_revision(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                proposed_change=" ",
                rationale="Regression failed",
                actor="operator:test",
            )


if __name__ == "__main__":
    unittest.main()
