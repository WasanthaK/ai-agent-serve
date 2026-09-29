import unittest

from db import get_connection, get_request, get_request_events, save_request


class DatabaseIntegrationTests(unittest.TestCase):
    def test_request_and_event_round_trip_on_fresh_schema(self):
        analysis = {
            "intent": "Request a quote",
            "category": "Plumbing",
            "summary": "Synthetic CI request",
            "urgency": "normal",
            "next_action": "Collect missing information",
            "needs_human_review": False,
            "missing_information": ["service_location"],
            "follow_up_questions": ["Where is the service required?"],
        }

        request_id = save_request(
            source="website",
            customer_name="CI Integration",
            message="Synthetic integration test request",
            result=analysis,
            skill_versions={"request_intake": "1.0.0"},
        )

        try:
            saved = get_request(request_id)
            self.assertIsNotNone(saved)
            self.assertEqual(saved["source"], "website")
            self.assertEqual(saved["status"], "needs_information")
            self.assertEqual(saved["missing_information"], ["service_location"])

            events = get_request_events(request_id)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "request_created")
            self.assertEqual(
                events[0]["details"]["skill_versions"],
                {"request_intake": "1.0.0"},
            )
        finally:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM agent_requests WHERE id = %s",
                        (request_id,),
                    )


if __name__ == "__main__":
    unittest.main()
