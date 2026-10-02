import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from db import get_connection
from provider_directory import create_provider
from provider_response_reliability import (
    calculate_provider_response_reliability,
    record_provider_response,
    record_response_opportunity,
)


class ProviderResponseReliabilityIntegrationTests(unittest.TestCase):
    def test_reliability_counts_timely_quotes_and_declines_without_penalizing_open_work(self):
        provider_id = uuid4()
        create_provider(
            "CI Response Reliability Provider",
            approval_status="approved",
            provider_id=provider_id,
        )

        as_of = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

        try:
            completed_specs = (
                ("quote", -20, 2),
                ("decline", -18, 3),
                ("quote", -16, 4),
                ("decline", -14, 6),
                ("quote", -12, 30),
            )
            first_response = None

            for index, (response_kind, offered_days, response_hours) in enumerate(
                completed_specs
            ):
                opportunity_id = uuid4()
                offered_at = as_of + timedelta(days=offered_days)
                deadline_at = offered_at + timedelta(hours=24)

                record_response_opportunity(
                    provider_id,
                    opportunity_id,
                    offered_at,
                    deadline_at,
                )
                response = record_provider_response(
                    provider_id,
                    opportunity_id,
                    response_kind,
                    offered_at + timedelta(hours=response_hours),
                )
                if index == 0:
                    first_response = (
                        opportunity_id,
                        response_kind,
                        offered_at + timedelta(hours=response_hours),
                        response["id"],
                    )

            no_response_id = uuid4()
            no_response_offer = as_of - timedelta(days=10)
            record_response_opportunity(
                provider_id,
                no_response_id,
                no_response_offer,
                no_response_offer + timedelta(hours=24),
            )

            open_id = uuid4()
            record_response_opportunity(
                provider_id,
                open_id,
                as_of - timedelta(hours=2),
                as_of + timedelta(hours=2),
            )

            old_id = uuid4()
            old_offer = as_of - timedelta(days=120)
            record_response_opportunity(
                provider_id,
                old_id,
                old_offer,
                old_offer + timedelta(hours=24),
            )
            record_provider_response(
                provider_id,
                old_id,
                "quote",
                old_offer + timedelta(hours=1),
            )

            metric = calculate_provider_response_reliability(
                provider_id,
                as_of=as_of,
            )

            self.assertEqual(metric["status"], "sufficient_history")
            self.assertEqual(metric["completed_opportunities"], 6)
            self.assertEqual(metric["on_time_responses"], 4)
            self.assertEqual(metric["late_responses"], 1)
            self.assertEqual(metric["no_responses"], 1)
            self.assertEqual(metric["reliability_bps"], 6666)

            duplicate = record_provider_response(
                provider_id,
                first_response[0],
                first_response[1],
                first_response[2],
            )
            self.assertEqual(duplicate["id"], first_response[3])
        finally:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM providers WHERE id = %s", (provider_id,))

    def test_fewer_than_five_completed_opportunities_is_unscored(self):
        provider_id = uuid4()
        create_provider(
            "CI Limited History Provider",
            approval_status="approved",
            provider_id=provider_id,
        )
        as_of = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

        try:
            for days_ago in (8, 7, 6, 5):
                opportunity_id = uuid4()
                offered_at = as_of - timedelta(days=days_ago)
                record_response_opportunity(
                    provider_id,
                    opportunity_id,
                    offered_at,
                    offered_at + timedelta(hours=24),
                )
                record_provider_response(
                    provider_id,
                    opportunity_id,
                    "decline",
                    offered_at + timedelta(hours=2),
                )

            metric = calculate_provider_response_reliability(
                provider_id,
                as_of=as_of,
            )

            self.assertEqual(metric["status"], "insufficient_history")
            self.assertEqual(metric["completed_opportunities"], 4)
            self.assertEqual(metric["on_time_responses"], 4)
            self.assertIsNone(metric["reliability_bps"])
        finally:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM providers WHERE id = %s", (provider_id,))


if __name__ == "__main__":
    unittest.main()
