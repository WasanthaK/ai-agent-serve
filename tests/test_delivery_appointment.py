import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID

import delivery_appointment as appointment


class DeliveryAppointmentTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        start_at = datetime.now(timezone.utc) + timedelta(days=1)
        end_at = start_at + timedelta(hours=1)

        with self.assertRaises(
            appointment.DeliveryAppointmentValidationError
        ):
            appointment.propose_delivery_appointment(
                UUID("11111111-1111-1111-1111-111111111111"),
                start_at,
                end_at,
                reason="Proposed window",
                actor="model:delivery",
            )

    def test_rejects_invalid_window(self):
        start_at = datetime.now(timezone.utc) + timedelta(days=1)

        with self.assertRaises(
            appointment.DeliveryAppointmentValidationError
        ):
            appointment.propose_delivery_appointment(
                UUID("11111111-1111-1111-1111-111111111111"),
                start_at,
                start_at,
                reason="Invalid window",
                actor="operator:test",
            )


if __name__ == "__main__":
    unittest.main()
