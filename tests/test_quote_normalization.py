import unittest
from uuid import uuid4

from quote_normalization import (
    QuoteNormalizationValidationError,
    normalize_structured_quote,
)


class QuoteNormalizationValidationTests(unittest.TestCase):
    def test_requires_operator_authority(self):
        with self.assertRaises(QuoteNormalizationValidationError):
            normalize_structured_quote(
                uuid4(),
                uuid4(),
                amount_minor=1000,
                currency="USD",
                scope_summary="Replace tap",
                actor="model:quote",
            )

    def test_currency_is_three_letters(self):
        for currency in ("US", "US12", "U$D"):
            with self.subTest(currency=currency):
                with self.assertRaises(QuoteNormalizationValidationError):
                    normalize_structured_quote(
                        uuid4(),
                        uuid4(),
                        amount_minor=1000,
                        currency=currency,
                        scope_summary="Replace tap",
                        actor="operator:test",
                    )

    def test_amount_and_duration_are_guarded(self):
        with self.assertRaises(QuoteNormalizationValidationError):
            normalize_structured_quote(
                uuid4(),
                uuid4(),
                amount_minor=-1,
                currency="USD",
                scope_summary="Replace tap",
                actor="operator:test",
            )

        with self.assertRaises(QuoteNormalizationValidationError):
            normalize_structured_quote(
                uuid4(),
                uuid4(),
                amount_minor=1000,
                currency="USD",
                scope_summary="Replace tap",
                estimated_duration_days=0,
                actor="operator:test",
            )

    def test_scope_and_list_items_cannot_be_blank(self):
        with self.assertRaises(QuoteNormalizationValidationError):
            normalize_structured_quote(
                uuid4(),
                uuid4(),
                amount_minor=1000,
                currency="USD",
                scope_summary=" ",
                actor="operator:test",
            )

        with self.assertRaises(QuoteNormalizationValidationError):
            normalize_structured_quote(
                uuid4(),
                uuid4(),
                amount_minor=1000,
                currency="USD",
                scope_summary="Replace tap",
                exclusions=[""],
                actor="operator:test",
            )


if __name__ == "__main__":
    unittest.main()
