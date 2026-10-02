import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from provider_response_reliability import (
    MIN_COMPLETED_OPPORTUNITIES,
    RELIABILITY_WINDOW_DAYS,
    ProviderResponseReliabilityValidationError,
    record_provider_response,
    record_response_opportunity,
)


class ProviderResponseReliabilityValidationTests(unittest.TestCase):
    def test_policy_constants_are_explicit(self):
        self.assertEqual(RELIABILITY_WINDOW_DAYS, 90)
        self.assertEqual(MIN_COMPLETED_OPPORTUNITIES, 5)

    def test_opportunity_rejects_naive_timestamps_before_database_access(self):
        with self.assertRaises(ProviderResponseReliabilityValidationError):
            record_response_opportunity(
                uuid4(),
                uuid4(),
                datetime(2026, 10, 1, 10, 0),
                datetime(2026, 10, 1, 12, 0),
            )

    def test_opportunity_requires_deadline_after_offer(self):
        offered_at = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)

        with self.assertRaises(ProviderResponseReliabilityValidationError):
            record_response_opportunity(
                uuid4(),
                uuid4(),
                offered_at,
                offered_at,
            )

    def test_response_kind_is_limited_to_quote_or_decline(self):
        with self.assertRaises(ProviderResponseReliabilityValidationError):
            record_provider_response(
                uuid4(),
                uuid4(),
                "ignored",
                datetime.now(timezone.utc),
            )

    def test_provider_and_opportunity_ids_must_be_uuid(self):
        now = datetime.now(timezone.utc)

        with self.assertRaises(ProviderResponseReliabilityValidationError):
            record_response_opportunity(
                "provider-id",
                uuid4(),
                now,
                now + timedelta(hours=1),
            )


if __name__ == "__main__":
    unittest.main()
