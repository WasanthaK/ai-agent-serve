import unittest
from datetime import datetime, timedelta, timezone
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

    def test_response_rejects_invalid_rating(self):
        with self.assertRaises(
            follow_up.SatisfactionFollowUpValidationError
        ):
            follow_up.record_satisfaction_response(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                rating=6,
                responded_at=datetime.now(timezone.utc),
                response_source="phone",
                actor="operator:test",
            )

    def test_response_rejects_future_timestamp(self):
        with self.assertRaises(
            follow_up.SatisfactionFollowUpValidationError
        ):
            follow_up.record_satisfaction_response(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                rating=5,
                responded_at=datetime.now(timezone.utc) + timedelta(days=1),
                response_source="phone",
                actor="operator:test",
            )


if __name__ == "__main__":
    unittest.main()
