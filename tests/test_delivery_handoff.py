import unittest
from uuid import UUID

import delivery_handoff as handoff


class DeliveryHandoffTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(handoff.DeliveryHandoffValidationError):
            handoff.activate_delivery_handoff(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                actor="model:delivery",
            )


if __name__ == "__main__":
    unittest.main()
