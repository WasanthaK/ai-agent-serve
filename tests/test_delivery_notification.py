import unittest
from uuid import UUID

import delivery_notification as notification


class DeliveryNotificationTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(
            notification.DeliveryNotificationValidationError
        ):
            notification.prepare_delivery_notifications(
                UUID("11111111-1111-1111-1111-111111111111"),
                actor="model:delivery",
            )

    def test_amount_format_is_deterministic(self):
        self.assertEqual(
            notification._format_amount(125000, "AUD"),
            "AUD 1250.00",
        )


if __name__ == "__main__":
    unittest.main()
