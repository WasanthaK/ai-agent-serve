import unittest
from unittest.mock import MagicMock, patch

import db
from agent_skills import DEFAULT_ANALYSIS_SKILLS, skill_registry
from tools import get_tool_version


ANALYSIS = {
    "intent": "request_quote",
    "category": "plumbing_tap_repair",
    "summary": "Replace a tap.",
    "urgency": "normal",
    "next_action": "Prepare quote",
    "needs_human_review": False,
    "missing_information": [],
    "follow_up_questions": [],
}


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, *args, **kwargs):
        return self.cursor_value


class FakeCursor:
    def __init__(self, fetchone_values=None):
        self.fetchone_values = list(fetchone_values or [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        return None

    def fetchone(self):
        return self.fetchone_values.pop(0)


class VersionProvenanceTests(unittest.TestCase):
    def test_default_skill_versions_are_explicit(self):
        versions = skill_registry.versions(DEFAULT_ANALYSIS_SKILLS)

        self.assertEqual(set(versions), set(DEFAULT_ANALYSIS_SKILLS))
        self.assertTrue(all(versions.values()))
        self.assertEqual(versions["request_intake"], "1.0.0")

    def test_registered_tool_version_is_explicit(self):
        self.assertEqual(
            get_tool_version("prepare_customer_follow_up"),
            "1.0.0",
        )

    def test_request_created_event_records_supplied_skill_versions(self):
        cursor = FakeCursor()
        versions = {"request_intake": "1.0.0"}

        with patch.object(
            db,
            "get_connection",
            return_value=FakeConnection(cursor),
        ), patch.object(db, "_record_event") as record:
            db.save_request(
                "website",
                None,
                "Replace a tap",
                dict(ANALYSIS),
                skill_versions=versions,
            )

        details = record.call_args.kwargs["details"]
        self.assertEqual(details["skill_versions"], versions)

    def test_request_reanalysed_event_records_supplied_skill_versions(self):
        cursor = FakeCursor(
            fetchone_values=[
                {"id": "request-id", "status": "needs_information"},
                {"id": "request-id", "status": "ready"},
            ]
        )
        versions = {"request_intake": "1.0.0"}

        with patch.object(
            db,
            "get_connection",
            return_value=FakeConnection(cursor),
        ), patch.object(db, "_record_event") as record:
            db.update_request_analysis(
                "request-id",
                dict(ANALYSIS),
                skill_versions=versions,
            )

        details = record.call_args.kwargs["details"]
        self.assertEqual(details["skill_versions"], versions)


if __name__ == "__main__":
    unittest.main()
