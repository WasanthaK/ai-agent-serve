import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import quote_completeness as completeness


class QuoteCompletenessTests(unittest.TestCase):
    def quote(self, **overrides):
        base = {
            "normalized_quote_id": "quote-1",
            "request_id": "request-1",
            "handoff_id": "handoff-1",
            "provider_id": "provider-1",
            "amount_minor": 10000,
            "currency": "USD",
            "scope_summary": "Replace kitchen tap",
            "exclusions": ["Wall repairs"],
            "terms": ["Payment on completion"],
            "available_from": None,
            "estimated_duration_days": None,
            "validity_expires_at": None,
        }
        base.update(overrides)
        return base

    def test_missing_exclusions_and_terms_is_incomplete(self):
        with patch.object(
            completeness,
            "get_normalized_quote",
            return_value=self.quote(exclusions=[], terms=[]),
        ):
            result = completeness.assess_quote_completeness(
                "request",
                "handoff",
                as_of=datetime(2026, 10, 2, tzinfo=timezone.utc),
            )

        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["comparison_ready"])
        self.assertTrue(result["requires_human_review"])
        self.assertEqual(
            result["missing_required_fields"],
            ["exclusions", "terms"],
        )

    def test_expired_quote_requires_human_review(self):
        as_of = datetime(2026, 10, 2, tzinfo=timezone.utc)
        with patch.object(
            completeness,
            "get_normalized_quote",
            return_value=self.quote(
                validity_expires_at=as_of - timedelta(minutes=1),
            ),
        ):
            result = completeness.assess_quote_completeness(
                "request",
                "handoff",
                as_of=as_of,
            )

        self.assertEqual(result["status"], "needs_human_review")
        self.assertFalse(result["comparison_ready"])
        self.assertEqual(result["blocking_reasons"], ["quote_expired"])

    def test_complete_quote_can_still_report_nonblocking_gaps(self):
        with patch.object(
            completeness,
            "get_normalized_quote",
            return_value=self.quote(),
        ):
            result = completeness.assess_quote_completeness(
                "request",
                "handoff",
                as_of=datetime(2026, 10, 2, tzinfo=timezone.utc),
            )

        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["comparison_ready"])
        self.assertTrue(result["requires_human_review"])
        self.assertEqual(
            result["informational_gaps"],
            [
                "available_from",
                "estimated_duration_days",
                "validity_expires_at",
            ],
        )
        self.assertFalse(result["evaluated"])
        self.assertFalse(result["recommended"])
        self.assertFalse(result["selected"])

    def test_missing_quote_raises_not_found(self):
        with patch.object(
            completeness,
            "get_normalized_quote",
            return_value=None,
        ):
            with self.assertRaises(
                completeness.QuoteCompletenessNotFoundError
            ):
                completeness.assess_quote_completeness(
                    "request",
                    "handoff",
                    as_of=datetime(2026, 10, 2, tzinfo=timezone.utc),
                )


if __name__ == "__main__":
    unittest.main()
