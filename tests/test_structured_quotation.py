import unittest
from datetime import datetime, timezone
from uuid import uuid4

from structured_quotation import (
    StructuredQuotationValidationError,
    record_structured_quotation,
)


class StructuredQuotationValidationTests(unittest.TestCase):
    def test_rejects_non_uppercase_currency(self):
        with self.assertRaises(StructuredQuotationValidationError):
            record_structured_quotation(
                uuid4(), uuid4(), currency="usd", total_amount_minor=100,
                scope_text="Repair tap", submitted_at=datetime.now(timezone.utc),
                actor="operator:test",
            )

    def test_rejects_fractional_or_negative_minor_units(self):
        for amount in (-1, 10.5):
            with self.assertRaises(StructuredQuotationValidationError):
                record_structured_quotation(
                    uuid4(), uuid4(), currency="USD", total_amount_minor=amount,
                    scope_text="Repair tap", submitted_at=datetime.now(timezone.utc),
                    actor="operator:test",
                )

    def test_requires_operator_authority(self):
        with self.assertRaises(StructuredQuotationValidationError):
            record_structured_quotation(
                uuid4(), uuid4(), currency="USD", total_amount_minor=100,
                scope_text="Repair tap", submitted_at=datetime.now(timezone.utc),
                actor="model:quote",
            )


if __name__ == "__main__":
    unittest.main()
