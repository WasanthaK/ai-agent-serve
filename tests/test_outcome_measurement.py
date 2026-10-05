import unittest

import outcome_measurement as outcome


class OutcomeMeasurementTests(unittest.TestCase):
    def test_requires_uuid_request_id(self):
        with self.assertRaises(
            outcome.OutcomeMeasurementValidationError
        ):
            outcome.get_outcome_measurement("not-a-uuid")


if __name__ == "__main__":
    unittest.main()
