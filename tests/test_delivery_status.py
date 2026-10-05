import unittest
from uuid import UUID

import delivery_status as status


class DeliveryStatusTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(status.DeliveryStatusValidationError):
            status.initialize_delivery_status(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                reason="Schedule delivery",
                actor="model:delivery",
            )

    def test_requires_reason(self):
        with self.assertRaises(status.DeliveryStatusValidationError):
            status.initialize_delivery_status(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                reason=" ",
                actor="operator:test",
            )

    def test_completion_requires_operator_actor(self):
        with self.assertRaises(status.DeliveryStatusValidationError):
            status.complete_delivery(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                reason="Work completed",
                actor="model:delivery",
            )


if __name__ == "__main__":
    unittest.main()
