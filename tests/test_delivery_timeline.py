import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

import delivery_timeline as timeline


class DeliveryTimelineTests(unittest.TestCase):
    def test_filters_non_delivery_events_and_preserves_future_delivery_events(self):
        request_id = UUID("11111111-1111-1111-1111-111111111111")
        now = datetime.now(timezone.utc)
        events = [
            {
                "id": UUID("00000000-0000-0000-0000-000000000001"),
                "request_id": request_id,
                "event_type": "request_created",
                "actor": "agent",
                "details": {},
                "correlation_id": "corr-1",
                "created_at": now,
            },
            {
                "id": UUID("00000000-0000-0000-0000-000000000002"),
                "request_id": request_id,
                "event_type": "delivery_handoff_activated",
                "actor": "operator:test",
                "details": {"provider_contacted": False},
                "correlation_id": "corr-2",
                "created_at": now,
            },
            {
                "id": UUID("00000000-0000-0000-0000-000000000003"),
                "request_id": request_id,
                "event_type": "delivery_future_event",
                "actor": "operator:test",
                "details": {"future": True},
                "correlation_id": "corr-3",
                "created_at": now,
            },
        ]

        with patch.object(
            timeline,
            "get_request_events",
            return_value=events,
        ):
            result = timeline.get_delivery_timeline(request_id)

        self.assertEqual(result["event_count"], 2)
        self.assertEqual(
            [item["sequence"] for item in result["timeline"]],
            [1, 2],
        )
        self.assertEqual(
            [item["event_type"] for item in result["timeline"]],
            [
                "delivery_handoff_activated",
                "delivery_future_event",
            ],
        )
        self.assertEqual(result["timeline"][0]["stage"], "handoff")
        self.assertTrue(result["timeline"][0]["known_event_type"])
        self.assertEqual(result["timeline"][1]["stage"], "delivery")
        self.assertFalse(result["timeline"][1]["known_event_type"])


if __name__ == "__main__":
    unittest.main()
