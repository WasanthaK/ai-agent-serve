import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

import quote_comparison as comparison


class QuoteComparisonTests(unittest.TestCase):
    def row(
        self,
        quote_id,
        handoff_id,
        provider_id,
        amount,
        currency="AUD",
        available_from=None,
        duration=None,
    ):
        return {
            "id": UUID(quote_id),
            "handoff_id": UUID(handoff_id),
            "provider_id": UUID(provider_id),
            "amount_minor": amount,
            "currency": currency,
            "scope_summary": "Replace kitchen tap",
            "exclusions": ["Wall repairs"],
            "terms": ["Payment on completion"],
            "available_from": available_from,
            "estimated_duration_days": duration,
            "validity_expires_at": None,
        }

    def test_mixed_currency_never_compares_price_or_selects(self):
        rows = [
            self.row(
                "11111111-1111-1111-1111-111111111111",
                "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "aaaaaaaa-1111-1111-1111-111111111111",
                10000,
                "AUD",
            ),
            self.row(
                "22222222-2222-2222-2222-222222222222",
                "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "bbbbbbbb-2222-2222-2222-222222222222",
                9000,
                "USD",
            ),
        ]

        conn = unittest.mock.MagicMock()
        cursor = unittest.mock.MagicMock()
        conn.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchall.return_value = rows

        with patch.object(comparison, "get_connection", return_value=conn),              patch.object(
                 comparison,
                 "assess_quote_completeness",
                 return_value={"comparison_ready": True},
             ):
            result = comparison.compare_request_quotes(
                UUID("99999999-9999-9999-9999-999999999999"),
                as_of=datetime(2026, 10, 2, tzinfo=timezone.utc),
            )

        self.assertFalse(result["price_comparable"])
        self.assertEqual(result["lowest_price_quote_ids"], [])
        self.assertIn("mixed_currencies", result["comparison_gaps"])
        self.assertIsNone(result["overall_winner_quote_id"])
        self.assertIsNone(result["recommended_quote_id"])
        self.assertIsNone(result["selected_quote_id"])

    def test_same_currency_reports_lowest_price_without_winner(self):
        rows = [
            self.row(
                "11111111-1111-1111-1111-111111111111",
                "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "aaaaaaaa-1111-1111-1111-111111111111",
                10000,
            ),
            self.row(
                "22222222-2222-2222-2222-222222222222",
                "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "bbbbbbbb-2222-2222-2222-222222222222",
                9000,
            ),
        ]

        conn = unittest.mock.MagicMock()
        cursor = unittest.mock.MagicMock()
        conn.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchall.return_value = rows

        with patch.object(comparison, "get_connection", return_value=conn),              patch.object(
                 comparison,
                 "assess_quote_completeness",
                 return_value={"comparison_ready": True},
             ):
            result = comparison.compare_request_quotes(
                UUID("99999999-9999-9999-9999-999999999999"),
                as_of=datetime(2026, 10, 2, tzinfo=timezone.utc),
            )

        self.assertTrue(result["price_comparable"])
        self.assertEqual(
            result["lowest_price_quote_ids"],
            ["22222222-2222-2222-2222-222222222222"],
        )
        self.assertIsNone(result["overall_winner_quote_id"])
        self.assertIsNone(result["recommended_quote_id"])
        self.assertIsNone(result["selected_quote_id"])

    def test_fewer_than_two_ready_quotes_fails_closed(self):
        row = self.row(
            "11111111-1111-1111-1111-111111111111",
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "aaaaaaaa-1111-1111-1111-111111111111",
            10000,
        )
        conn = unittest.mock.MagicMock()
        cursor = unittest.mock.MagicMock()
        conn.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchall.return_value = [row]

        with patch.object(comparison, "get_connection", return_value=conn),              patch.object(
                 comparison,
                 "assess_quote_completeness",
                 return_value={"comparison_ready": True},
             ):
            with self.assertRaises(
                comparison.QuoteComparisonNotReadyError
            ):
                comparison.compare_request_quotes(
                    UUID("99999999-9999-9999-9999-999999999999"),
                    as_of=datetime(2026, 10, 2, tzinfo=timezone.utc),
                )


if __name__ == "__main__":
    unittest.main()
