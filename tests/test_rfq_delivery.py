import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from rfq_delivery import (
    RFQDeliveryValidationError,
    authorize_rfq_delivery,
    confirm_rfq_delivery,
)


class RFQDeliveryValidationTests(unittest.TestCase):
    def test_authorization_requires_operator_actor(self):
        for actor in ("", "agent", "model:routing"):
            with self.subTest(actor=actor):
                with self.assertRaises(RFQDeliveryValidationError):
                    authorize_rfq_delivery(
                        uuid4(),
                        uuid4(),
                        actor=actor,
                    )

    def test_confirmation_requires_timezone_aware_deadline(self):
        with self.assertRaises(RFQDeliveryValidationError):
            confirm_rfq_delivery(
                uuid4(),
                uuid4(),
                datetime(2026, 10, 2, 12, 0),
                actor="operator:test",
            )

    def test_request_and_handoff_ids_must_be_uuid(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        with self.assertRaises(RFQDeliveryValidationError):
            confirm_rfq_delivery(
                "request-id",
                uuid4(),
                future,
                actor="operator:test",
            )


if __name__ == "__main__":
    unittest.main()
