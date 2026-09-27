import json
import unittest
from unittest.mock import patch

import idempotency


class FakeCursor:
    def __init__(self, rowcounts):
        self._rowcounts = iter(rowcounts)
        self.rowcount = 0
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=None):
        self.statements.append((statement, params))
        self.rowcount = next(self._rowcounts)


class FakeConnection:
    def __init__(self, rowcounts):
        self.cursor_instance = FakeCursor(rowcounts)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, *args, **kwargs):
        return self.cursor_instance


class RetryRecoveryTests(unittest.TestCase):
    def test_recovery_completes_committed_and_releases_orphaned_reservations(self):
        connection = FakeConnection([2, 3])

        with patch.object(idempotency, "get_connection", return_value=connection):
            result = idempotency.recover_incomplete_webhook_deliveries()

        self.assertEqual(result, {"completed": 2, "released": 3})
        self.assertEqual(len(connection.cursor_instance.statements), 2)

        update_sql = connection.cursor_instance.statements[0][0]
        delete_sql = connection.cursor_instance.statements[1][0]
        self.assertIn("UPDATE webhook_idempotency", update_sql)
        self.assertIn("EXISTS", update_sql)
        self.assertIn("agent_requests", update_sql)
        self.assertIn("DELETE FROM webhook_idempotency", delete_sql)
        self.assertIn("NOT EXISTS", delete_sql)
        self.assertIn("agent_requests", delete_sql)

    def test_recovery_log_contains_only_controlled_counts(self):
        connection = FakeConnection([1, 4])

        with patch.object(idempotency, "get_connection", return_value=connection), \
             self.assertLogs("agent.idempotency", level="INFO") as captured:
            idempotency.recover_incomplete_webhook_deliveries()

        payload = json.loads(captured.output[-1].split(":", 2)[-1])
        self.assertEqual(payload, {
            "event": "idempotency_recovery_completed",
            "completed": 1,
            "released": 4,
        })
        rendered = captured.output[-1]
        for forbidden in (
            "idempotency_key_hash",
            "payload_hash",
            "request_id",
            "source",
        ):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
