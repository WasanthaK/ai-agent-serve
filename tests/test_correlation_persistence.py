import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

import db


ANALYSIS = {
    "intent": "quote_request",
    "category": "plumbing",
    "summary": "Leaking tap",
    "urgency": "normal",
    "next_action": "Arrange plumber",
    "needs_human_review": False,
    "missing_information": [],
    "follow_up_questions": [],
}


class CorrelationPersistenceTests(unittest.TestCase):
    def connection_with_cursor(self):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        return connection, cursor

    def test_request_creation_persists_current_correlation_id(self):
        correlation_id = str(uuid4())
        connection, cursor = self.connection_with_cursor()

        with patch.object(db, "get_connection", return_value=connection), \
             patch.object(db, "get_correlation_id", return_value=correlation_id), \
             patch.object(db, "_record_event"):
            db.save_request(
                "website",
                "Test Customer",
                "My tap is leaking",
                dict(ANALYSIS),
            )

        sql, params = cursor.execute.call_args_list[0].args
        self.assertIn("correlation_id", sql)
        self.assertEqual(params[-1], correlation_id)

    def test_event_persists_current_correlation_id(self):
        correlation_id = str(uuid4())
        request_id = uuid4()
        cursor = MagicMock()

        with patch.object(db, "get_correlation_id", return_value=correlation_id):
            db._record_event(
                cursor,
                request_id=request_id,
                event_type="request_tested",
                actor="agent",
                details={"safe": True},
            )

        sql, params = cursor.execute.call_args.args
        self.assertIn("correlation_id", sql)
        self.assertEqual(params[-1], correlation_id)

    def test_message_persists_current_correlation_id(self):
        correlation_id = str(uuid4())
        connection, cursor = self.connection_with_cursor()
        cursor.fetchone.return_value = {"id": uuid4(), "message": "More info"}

        with patch.object(db, "get_connection", return_value=connection), \
             patch.object(db, "get_correlation_id", return_value=correlation_id), \
             patch.object(db, "_record_event"):
            db.save_message(
                request_id=uuid4(),
                role="customer",
                channel="website",
                message="More info",
            )

        sql, params = cursor.execute.call_args_list[0].args
        self.assertIn("correlation_id", sql)
        self.assertEqual(params[-1], correlation_id)

    def test_background_write_allows_null_correlation_id(self):
        connection, cursor = self.connection_with_cursor()

        with patch.object(db, "get_connection", return_value=connection), \
             patch.object(db, "get_correlation_id", return_value=None), \
             patch.object(db, "_record_event"):
            db.save_request(
                "system",
                None,
                "Background task",
                dict(ANALYSIS),
            )

        _, params = cursor.execute.call_args_list[0].args
        self.assertIsNone(params[-1])


if __name__ == "__main__":
    unittest.main()
