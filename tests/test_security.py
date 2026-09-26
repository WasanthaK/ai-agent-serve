import importlib
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from tools import ToolExecutionError


INBOUND_KEY = "inbound-" + "a" * 40
OPERATOR_KEY = "operator-" + "b" * 40
VIEWER_KEY = "viewer-" + "c" * 40
ROTATED_INBOUND_KEY = "inbound-new-" + "d" * 40
ROTATED_OPERATOR_KEY = "operator-new-" + "e" * 40
OPERATORS = [
    {"id": "wasantha", "key": OPERATOR_KEY,
     "permissions": ["read", "analyze", "reply", "decide", "tools"]},
    {"id": "viewer", "key": VIEWER_KEY, "permissions": ["read"]},
]

with patch.dict(os.environ, {
    "OPENAI_API_KEY": "test-only-key",
    "AGENT_INBOUND_API_KEY": INBOUND_KEY,
    "AGENT_OPERATOR_CREDENTIALS": json.dumps(OPERATORS),
    "AGENT_INBOUND_SOURCE": "website",
}):
    security = importlib.import_module("security")
    api = importlib.import_module("app")


class APIKeyConfigurationTests(unittest.TestCase):
    def test_missing_short_and_shared_keys_are_rejected(self):
        for inbound, operators in (
            ("", OPERATORS),
            ("short", OPERATORS),
            (INBOUND_KEY, [{**OPERATORS[0], "key": INBOUND_KEY}]),
            (INBOUND_KEY, [{**OPERATORS[0], "key": "has whitespace " + "b" * 40}]),
            (INBOUND_KEY, [OPERATORS[0], {**OPERATORS[1], "key": OPERATOR_KEY}]),
        ):
            with self.subTest(inbound=inbound[:10], operators=operators):
                with patch.dict(os.environ, {
                    "AGENT_INBOUND_API_KEY": inbound,
                    "AGENT_OPERATOR_CREDENTIALS": json.dumps(operators),
                }):
                    with self.assertRaises(RuntimeError):
                        security.load_credentials()

    def test_invalid_operator_configuration_is_rejected(self):
        invalid_entries = (
            [],
            [{**OPERATORS[0], "permissions": ["unknown"]}],
            [{**OPERATORS[0], "permissions": ["read", "read"]}],
            [OPERATORS[0], {**OPERATORS[1], "id": "wasantha"}],
            [{**OPERATORS[0], "id": "bad id"}],
            [{"id": "wasantha", "key": OPERATOR_KEY}],
        )
        for entries in invalid_entries:
            with self.subTest(entries=entries):
                with patch.dict(os.environ, {
                    "AGENT_OPERATOR_CREDENTIALS": json.dumps(entries),
                }):
                    with self.assertRaises(RuntimeError):
                        security.load_credentials()

    def test_rotation_accepts_two_distinct_keys_and_can_revoke_old_key(self):
        rotating_operators = [
            {"id": "wasantha", "keys": [OPERATOR_KEY, ROTATED_OPERATOR_KEY],
             "permissions": ["read", "analyze", "reply", "decide", "tools"]},
        ]
        with patch.dict(os.environ, {
            "AGENT_INBOUND_API_KEY": "",
            "AGENT_INBOUND_API_KEYS": json.dumps([INBOUND_KEY, ROTATED_INBOUND_KEY]),
            "AGENT_OPERATOR_CREDENTIALS": json.dumps(rotating_operators),
        }):
            inbound_digests, operators = security.load_credentials()
        self.assertEqual(len(inbound_digests), 2)
        self.assertEqual([operator.actor for _, operator in operators],
            ["operator:wasantha", "operator:wasantha"])

        with patch.object(security, "_INBOUND_DIGESTS", inbound_digests), \
             patch.object(security, "_OPERATORS", operators), \
             patch.object(api, "analyze_quote_request", return_value={"category": "plumbing"}), \
             patch.object(api, "save_request", return_value=uuid4()), \
             patch.object(api, "get_request", return_value={"status": "ready"}):
            for key in (INBOUND_KEY, ROTATED_INBOUND_KEY):
                response = TestClient(api.app).post("/webhook/quote-request",
                    json={"source": "website", "message": "Test"},
                    headers={"X-API-Key": key})
                self.assertEqual(response.status_code, 200)
            for key in (OPERATOR_KEY, ROTATED_OPERATOR_KEY):
                response = TestClient(api.app).get(f"/requests/{uuid4()}",
                    headers={"X-API-Key": key})
                self.assertEqual(response.status_code, 200)

        with patch.dict(os.environ, {
            "AGENT_INBOUND_API_KEY": ROTATED_INBOUND_KEY,
            "AGENT_INBOUND_API_KEYS": "",
            "AGENT_OPERATOR_CREDENTIALS": json.dumps([
                {**rotating_operators[0], "keys": [ROTATED_OPERATOR_KEY]},
            ]),
        }):
            new_inbound, new_operators = security.load_credentials()
        with patch.object(security, "_INBOUND_DIGESTS", new_inbound), \
             patch.object(security, "_OPERATORS", new_operators), \
             patch.object(security.security_logger, "warning"):
            self.assertEqual(TestClient(api.app).post("/webhook/quote-request",
                json={"source": "website", "message": "Test"},
                headers={"X-API-Key": INBOUND_KEY}).status_code, 401)
            self.assertEqual(TestClient(api.app).get(f"/requests/{uuid4()}",
                headers={"X-API-Key": OPERATOR_KEY}).status_code, 401)

    def test_rotation_rejects_ambiguous_or_duplicate_keys(self):
        configurations = (
            {"AGENT_INBOUND_API_KEY": INBOUND_KEY,
             "AGENT_INBOUND_API_KEYS": json.dumps([INBOUND_KEY, ROTATED_INBOUND_KEY])},
            {"AGENT_INBOUND_API_KEY": "",
             "AGENT_INBOUND_API_KEYS": json.dumps([INBOUND_KEY, INBOUND_KEY])},
            {"AGENT_INBOUND_API_KEY": "",
             "AGENT_INBOUND_API_KEYS": json.dumps([INBOUND_KEY] * 3)},
            {"AGENT_OPERATOR_CREDENTIALS": json.dumps([
                {**OPERATORS[0], "keys": [OPERATOR_KEY, OPERATOR_KEY], "key": OPERATOR_KEY},
            ])},
        )
        for configuration in configurations:
            with self.subTest(configuration=configuration):
                with patch.dict(os.environ, configuration):
                    with self.assertRaises(RuntimeError):
                        security.load_credentials()

    def test_inbound_source_must_be_configured(self):
        for source in ("", " website", "other channel"):
            with self.subTest(source=source):
                with patch.dict(os.environ, {"AGENT_INBOUND_SOURCE": source}):
                    with self.assertRaises(RuntimeError):
                        security.load_inbound_source()


class RouteAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        self.request_id = uuid4()
        audit_patch = patch.object(security.security_logger, "warning")
        self.audit_log = audit_patch.start()
        self.addCleanup(audit_patch.stop)

    def test_denials_log_only_controlled_metadata(self):
        body_secret = "private-customer-message-marker"
        invalid_key = "private-invalid-api-key-" + "x" * 40
        response = self.client.post("/agent", json={"message": body_secret},
            headers={"X-API-Key": invalid_key})
        self.assertEqual(response.status_code, 401)
        event = json.loads(self.audit_log.call_args.args[0])
        self.assertEqual(event, {
            "event": "access_denied", "reason": "invalid_operator_credential",
            "method": "POST", "route": "/agent", "actor": None,
        })
        self.assertNotIn(invalid_key, self.audit_log.call_args.args[0])
        self.assertNotIn(body_secret, self.audit_log.call_args.args[0])

        response = self.client.post(f"/requests/{self.request_id}/approve",
            json={"reason": body_secret}, headers={"X-API-Key": VIEWER_KEY})
        self.assertEqual(response.status_code, 403)
        event = json.loads(self.audit_log.call_args.args[0])
        self.assertEqual(event["actor"], "operator:viewer")
        self.assertEqual(event["route"], "/requests/{request_id}/approve")
        self.assertNotIn(body_secret, self.audit_log.call_args.args[0])

    def test_public_routes_remain_public(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/service-catalog").status_code, 200)

    def test_every_private_route_rejects_missing_and_wrong_role_keys(self):
        paths = [
            ("POST", "/agent", {"message": "Test"}, OPERATOR_KEY, INBOUND_KEY),
            ("POST", "/webhook/quote-request", {"source": "test", "message": "Test"}, INBOUND_KEY, OPERATOR_KEY),
            ("POST", f"/webhook/quote-request/{self.request_id}/reply", {"message": "Test"}, INBOUND_KEY, OPERATOR_KEY),
            ("GET", f"/requests/{self.request_id}", None, OPERATOR_KEY, INBOUND_KEY),
            ("GET", f"/requests/{self.request_id}/events", None, OPERATOR_KEY, INBOUND_KEY),
            ("GET", f"/requests/{self.request_id}/messages", None, OPERATOR_KEY, INBOUND_KEY),
            ("POST", f"/requests/{self.request_id}/reply", {"message": "Test"}, OPERATOR_KEY, INBOUND_KEY),
            ("POST", f"/requests/{self.request_id}/approve", {}, OPERATOR_KEY, INBOUND_KEY),
            ("POST", f"/requests/{self.request_id}/reject", {}, OPERATOR_KEY, INBOUND_KEY),
            ("POST", f"/requests/{self.request_id}/tools/prepare_customer_follow_up", None, OPERATOR_KEY, INBOUND_KEY),
        ]
        for method, path, body, correct, wrong in paths:
            with self.subTest(path=path):
                for key in (None, wrong, "invalid-" + "z" * 40):
                    headers = {"X-API-Key": key} if key else {}
                    response = self.client.request(method, path, json=body, headers=headers)
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.json(), {"detail": "Invalid API credentials"})

                if path.startswith("/requests/") or path.endswith("/reply"):
                    with patch.object(api, "get_request", return_value=None):
                        response = self.client.request(method, path, json=body,
                            headers={"X-API-Key": correct})
                    self.assertEqual(response.status_code, 404)

    def test_inbound_credential_can_create_request(self):
        analysis = {"category": "plumbing"}
        with patch.object(api, "analyze_quote_request", return_value=analysis), \
             patch.object(api, "save_request", return_value=self.request_id), \
             patch.object(api, "get_request", return_value={"status": "ready"}):
            response = self.client.post("/webhook/quote-request",
                json={"source": "website", "message": "A leaking tap"},
                headers={"X-API-Key": INBOUND_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["workflow_status"], "ready")

    def test_inbound_source_cannot_be_spoofed(self):
        with patch.object(api, "analyze_quote_request") as analyze, \
             patch.object(api, "save_request") as save:
            response = self.client.post("/webhook/quote-request",
                json={"source": "other-channel", "message": "Test"},
                headers={"X-API-Key": INBOUND_KEY})
        self.assertEqual(response.status_code, 403)
        analyze.assert_not_called()
        save.assert_not_called()

    def test_inbound_reply_only_updates_owned_request(self):
        path = f"/webhook/quote-request/{self.request_id}/reply"
        owned = {
            "source": "website", "status": "needs_information",
            "message": "A leaking tap", "customer_name": "Test",
        }
        with patch.object(api, "get_request", return_value=owned), \
             patch.object(api, "save_message", return_value={"message": "More info"}) as save, \
             patch.object(api, "get_request_messages", return_value=[]), \
             patch.object(api, "analyze_quote_request", return_value={"category": "plumbing"}), \
             patch.object(api, "update_request_analysis", return_value={"status": "ready"}):
            response = self.client.post(path, json={"message": "More info"},
                headers={"X-API-Key": INBOUND_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(save.call_args.kwargs["channel"], "website")
        self.assertEqual(save.call_args.kwargs["actor"], "channel:website")

        for request in (None, {**owned, "source": "other-channel"}):
            with self.subTest(request=request), \
                 patch.object(api, "get_request", return_value=request), \
                 patch.object(api, "save_message") as save:
                response = self.client.post(path, json={"message": "More info"},
                    headers={"X-API-Key": INBOUND_KEY})
                self.assertEqual(response.status_code, 404)
                save.assert_not_called()

        with patch.object(api, "get_request", return_value=owned), \
             patch.object(api, "save_message") as save:
            response = self.client.post(path,
                json={"message": "More info", "channel": "other-channel"},
                headers={"X-API-Key": INBOUND_KEY})
            self.assertEqual(response.status_code, 403)
            save.assert_not_called()

        with patch.object(api, "get_request", return_value={**owned, "status": "ready"}), \
             patch.object(api, "save_message") as save:
            response = self.client.post(path, json={"message": "Late reply"},
                headers={"X-API-Key": INBOUND_KEY})
            self.assertEqual(response.status_code, 409)
            save.assert_not_called()

    def test_operator_reply_path_remains_available(self):
        request = {
            "source": "another-channel", "status": "needs_information",
            "message": "Initial request", "customer_name": "Test",
        }
        with patch.object(api, "get_request", return_value=request), \
             patch.object(api, "save_message", return_value={"message": "Details"}) as save, \
             patch.object(api, "get_request_messages", return_value=[]), \
             patch.object(api, "analyze_quote_request", return_value={"category": "plumbing"}), \
             patch.object(api, "update_request_analysis", return_value={"status": "ready"}):
            response = self.client.post(f"/requests/{self.request_id}/reply",
                json={"message": "Details"}, headers={"X-API-Key": OPERATOR_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(save.call_args.kwargs["channel"], "another-channel")
        self.assertEqual(save.call_args.kwargs["actor"], "operator:wasantha")

    def test_read_only_operator_cannot_decide_execute_reply_or_analyze(self):
        paths = [
            ("POST", "/agent", {"message": "Test"}),
            ("POST", f"/requests/{self.request_id}/reply", {"message": "Test"}),
            ("POST", f"/requests/{self.request_id}/approve", {}),
            ("POST", f"/requests/{self.request_id}/reject", {}),
            ("POST", f"/requests/{self.request_id}/tools/prepare_customer_follow_up", None),
        ]
        with patch.object(api, "get_request") as get_request, \
             patch.object(api, "analyze_quote_request") as analyze:
            for method, path, body in paths:
                with self.subTest(path=path):
                    response = self.client.request(method, path, json=body,
                        headers={"X-API-Key": VIEWER_KEY})
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json(), {"detail": "Operator permission denied"})
            get_request.assert_not_called()
            analyze.assert_not_called()

        with patch.object(api, "get_request", return_value=None):
            response = self.client.get(f"/requests/{self.request_id}",
                headers={"X-API-Key": VIEWER_KEY})
        self.assertEqual(response.status_code, 404)

    def test_operator_identity_is_not_taken_from_body(self):
        with patch.object(api, "get_request", return_value={"status": "awaiting_human_review"}), \
             patch.object(api, "update_request_status", return_value={"status": "approved"}) as update:
            response = self.client.post(f"/requests/{self.request_id}/approve",
                json={"actor": "spoofed administrator", "reason": "Reviewed"},
                headers={"X-API-Key": OPERATOR_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(update.call_args.kwargs["actor"], "operator:wasantha")

    def test_rejection_and_tool_events_use_authenticated_operator(self):
        with patch.object(api, "get_request", return_value={"status": "ready"}), \
             patch.object(api, "update_request_status", return_value={"status": "rejected"}) as update:
            response = self.client.post(f"/requests/{self.request_id}/reject",
                json={"actor": "someone-else"}, headers={"X-API-Key": OPERATOR_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(update.call_args.kwargs["actor"], "operator:wasantha")

        with patch.object(api, "get_request", return_value={"status": "needs_information"}), \
             patch.object(api, "execute_tool", return_value={"delivery_status": "draft_only"}), \
             patch.object(api, "record_event") as record:
            response = self.client.post(
                f"/requests/{self.request_id}/tools/prepare_customer_follow_up",
                headers={"X-API-Key": OPERATOR_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([call.kwargs["actor"] for call in record.call_args_list],
            ["operator:wasantha", "operator:wasantha"])

    def test_tool_events_and_errors_omit_customer_content(self):
        result = {"message": "private-customer-message-marker", "delivery_status": "draft_only"}
        with patch.object(api, "get_request", return_value={"status": "needs_information"}), \
             patch.object(api, "execute_tool", return_value=result), \
             patch.object(api, "record_event") as record:
            response = self.client.post(
                f"/requests/{self.request_id}/tools/prepare_customer_follow_up",
                headers={"X-API-Key": OPERATOR_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(record.call_args.kwargs["details"],
            {"tool": "prepare_customer_follow_up"})

        with patch.object(api, "get_request", return_value={"status": "needs_information"}), \
             patch.object(api, "execute_tool", side_effect=ToolExecutionError("private-token-marker")), \
             patch.object(api, "record_event") as record:
            response = self.client.post(
                f"/requests/{self.request_id}/tools/prepare_customer_follow_up",
                headers={"X-API-Key": OPERATOR_KEY})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Tool could not be executed")
        self.assertEqual(record.call_args.kwargs["details"], {
            "tool": "prepare_customer_follow_up", "error_type": "ToolExecutionError",
        })

    def test_model_errors_have_generic_response(self):
        with patch.object(api.client.responses, "create",
                          side_effect=RuntimeError("private-provider-token-marker")):
            response = self.client.post("/agent", json={"message": "Test"},
                headers={"X-API-Key": OPERATOR_KEY})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"],
            "Request analysis is temporarily unavailable")


if __name__ == "__main__":
    unittest.main()
