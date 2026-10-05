import unittest
from datetime import datetime, timezone
from uuid import UUID

import delivery_exception as exception


class DeliveryExceptionTests(unittest.TestCase):
    def test_requires_operator_actor(self):
        with self.assertRaises(exception.DeliveryExceptionValidationError):
            exception.record_delivery_exception(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                UUID("33333333-3333-3333-3333-333333333333"),
                "delay",
                datetime.now(timezone.utc),
                summary="Provider delayed",
                actor="model:delivery",
            )

    def test_rejects_unknown_exception_kind(self):
        with self.assertRaises(exception.DeliveryExceptionValidationError):
            exception.record_delivery_exception(
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                UUID("33333333-3333-3333-3333-333333333333"),
                "other",
                datetime.now(timezone.utc),
                summary="Unknown event",
                actor="operator:test",
            )


if __name__ == "__main__":
    unittest.main()
