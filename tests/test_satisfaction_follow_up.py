import unittest
from uuid import UUID

import satisfaction_follow_up as follow_up


class SatisfactionFollowUpTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(
            follow_up.SatisfactionFollowUpValidationError
        ):
            follow_up.prepare_satisfaction_follow_up(
                UUID("11111111-1111-1111-1111-111111111111"),
                actor="model:closure",
            )


if __name__ == "__main__":
    unittest.main()
