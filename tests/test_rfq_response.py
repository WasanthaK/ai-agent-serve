import unittest
from datetime import datetime, timezone
from uuid import uuid4

from rfq_response import (
    RFQResponseValidationError,
    ingest_rfq_response,
)


class RFQResponseValidationTests(unittest.TestCase):
    def test_response_kind_is_closed_set(self):
        with self.assertRaises(RFQResponseValidationError):
            ingest_rfq_response(
                uuid4(), uuid4(), "maybe",
                datetime.now(timezone.utc),
                actor="operator:test",
            )

    def test_response_requires_timezone_aware_timestamp(self):
        with self.assertRaises(RFQResponseValidationError):
            ingest_rfq_response(
                uuid4(), uuid4(), "quote",
                datetime(2026, 10, 2, 12, 0),
                actor="operator:test",
            )

    def test_response_requires_operator_actor(self):
        with self.assertRaises(RFQResponseValidationError):
            ingest_rfq_response(
                uuid4(), uuid4(), "decline",
                datetime.now(timezone.utc),
                actor="model:routing",
            )


if __name__ == "__main__":
    unittest.main()
