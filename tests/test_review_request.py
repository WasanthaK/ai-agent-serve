import unittest
from uuid import UUID

import review_request as review


class ReviewRequestTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(review.ReviewRequestValidationError):
            review.prepare_review_request(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                reason="Prepare public review request",
                actor="model:closure",
            )

    def test_requires_reason(self):
        with self.assertRaises(review.ReviewRequestValidationError):
            review.prepare_review_request(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                reason=" ",
                actor="operator:test",
            )


if __name__ == "__main__":
    unittest.main()
