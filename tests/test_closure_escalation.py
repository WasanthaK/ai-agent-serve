import unittest
from uuid import UUID

import closure_escalation as escalation


class ClosureEscalationTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(
            escalation.ClosureEscalationValidationError
        ):
            escalation.create_closure_escalation(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                "complaint",
                priority="high",
                reason="Customer complaint",
                actor="model:closure",
            )

    def test_rejects_unknown_kind(self):
        with self.assertRaises(
            escalation.ClosureEscalationValidationError
        ):
            escalation.create_closure_escalation(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                "refund",
                priority="high",
                reason="Customer complaint",
                actor="operator:test",
            )

    def test_rejects_unknown_priority(self):
        with self.assertRaises(
            escalation.ClosureEscalationValidationError
        ):
            escalation.create_closure_escalation(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                "rework",
                priority="critical",
                reason="Rework review",
                actor="operator:test",
            )


if __name__ == "__main__":
    unittest.main()
