import unittest
from uuid import UUID

import human_intervention as intervention


class HumanInterventionTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(
            intervention.HumanInterventionValidationError
        ):
            intervention.create_human_intervention(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                priority="high",
                reason="Needs review",
                actor="model:delivery",
            )

    def test_rejects_unknown_priority(self):
        with self.assertRaises(
            intervention.HumanInterventionValidationError
        ):
            intervention.create_human_intervention(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                priority="critical",
                reason="Needs review",
                actor="operator:test",
            )


if __name__ == "__main__":
    unittest.main()
