import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

import db


def analysis():
    return {
        "intent": "quote_request",
        "category": "plumbing",
        "summary": "Private customer summary marker",
        "urgency": "normal",
        "next_action": "Clarify",
        "needs_human_review": False,
        "missing_information": ["Private customer detail marker"],
        "follow_up_questions": ["Private question marker"],
    }


class EventPrivacyTests(unittest.TestCase):
    def setUp(self):
        connection = MagicMock()
        self.cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        connection_patch = patch.object(db, "get_connection", return_value=connection)
        self.record_patch = patch.object(db, "_record_event")
        connection_patch.start()
        self.record = self.record_patch.start()
        self.addCleanup(connection_patch.stop)
        self.addCleanup(self.record_patch.stop)

    def test_creation_event_counts_missing_information_without_copying_content(self):
        db.save_request("website", "Private name marker", "Private message marker", analysis())
        details = self.record.call_args.kwargs["details"]
        self.assertEqual(details["missing_information_count"], 1)
        self.assertNotIn("missing_information", details)
        self.assertNotIn("Private", str(details))

    def test_reanalysis_event_counts_missing_information_without_copying_content(self):
        self.cursor.fetchone.side_effect = [
            {"status": "needs_information"}, {"status": "needs_information"},
        ]
        db.update_request_analysis(uuid4(), analysis())
        details = self.record.call_args.kwargs["details"]
        self.assertEqual(details["missing_information_count"], 1)
        self.assertNotIn("missing_information", details)
        self.assertNotIn("Private", str(details))


if __name__ == "__main__":
    unittest.main()
