import unittest
from uuid import uuid4

from rfq_handoff import (
    RFQHandoffValidationError,
    prepare_rfq_handoff,
)


class RFQHandoffValidationTests(unittest.TestCase):
    def test_request_id_must_be_uuid(self):
        with self.assertRaises(RFQHandoffValidationError):
            prepare_rfq_handoff(
                "request-id",
                actor="operator:test",
            )

    def test_preparation_requires_operator_authority_before_database_access(self):
        for actor in ("", "agent", "model:quote_preparation"):
            with self.subTest(actor=actor):
                with self.assertRaises(RFQHandoffValidationError):
                    prepare_rfq_handoff(
                        uuid4(),
                        actor=actor,
                    )


if __name__ == "__main__":
    unittest.main()
