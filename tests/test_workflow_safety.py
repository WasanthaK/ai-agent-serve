import unittest

from db import _apply_safety_precedence


class SafetyPrecedenceTests(unittest.TestCase):
    def test_human_review_clears_clarification_fields(self):
        result = {
            "needs_human_review": True,
            "missing_information": ["Whether there is smoke or fire"],
            "follow_up_questions": ["Is there smoke or fire?"],
        }

        returned = _apply_safety_precedence(result)

        self.assertIs(returned, result)
        self.assertEqual(result["missing_information"], [])
        self.assertEqual(result["follow_up_questions"], [])

    def test_non_escalated_request_keeps_clarification_fields(self):
        result = {
            "needs_human_review": False,
            "missing_information": ["Property address"],
            "follow_up_questions": ["What is the property address?"],
        }

        _apply_safety_precedence(result)

        self.assertEqual(result["missing_information"], ["Property address"])
        self.assertEqual(
            result["follow_up_questions"],
            ["What is the property address?"],
        )


if __name__ == "__main__":
    unittest.main()
