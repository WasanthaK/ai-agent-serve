import unittest
from unittest.mock import patch
from uuid import UUID

import quote_award as award


class QuoteAwardTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(award.QuoteAwardValidationError):
            award.award_recommended_quote(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                reason="Human award",
                actor="model:quote-evaluation",
            )

    def test_reason_is_required(self):
        with self.assertRaises(award.QuoteAwardValidationError):
            award.award_recommended_quote(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                reason=" ",
                actor="operator:test",
            )


if __name__ == "__main__":
    unittest.main()
