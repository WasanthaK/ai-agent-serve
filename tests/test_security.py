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


def inbound_persistence_result():
    return {
        "action": "created",
        "message": {
            "id": uuid4(),
            "linked_request_id": None,
        },
    }


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
             patch.object(api, "save_inbound_message", return_value=inbound_persistence_result()), \
             patch.object(api, "link_inbound_message_to_request"), \
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

    def test_provider_selection_requires_decide_permission(self):
        provider_id = uuid4()
        payload = {
            "service_slug": "plumbing",
            "area_key": "bn:brunei-muara",
            "provider_ids": [str(provider_id)],
            "reason": "Human routing decision",
        }

        with patch.object(
            api,
            "select_providers_for_request",
            return_value={
                "request_id": str(self.request_id),
                "selected_provider_ids": [str(provider_id)],
                "selection_authority": "human",
                "ranked": False,
            },
        ) as select:
            denied = self.client.post(
                f"/requests/{self.request_id}/provider-selection",
                json=payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            select.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/provider-selection",
                json=payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                select.call_args.kwargs["actor"],
                "operator:wasantha",
            )

        with patch.object(
            api,
            "get_provider_selection",
            return_value={
                "request_id": str(self.request_id),
                "selected_provider_ids": [str(provider_id)],
            },
        ):
            readable = self.client.get(
                f"/requests/{self.request_id}/provider-selection",
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(readable.status_code, 200)

    def test_rfq_handoff_preparation_requires_decide_permission(self):
        prepared = {
            "rfq_id": str(uuid4()),
            "request_id": str(self.request_id),
            "status": "prepared",
            "provider_handoffs": [],
            "delivery_started": False,
        }

        with patch.object(
            api,
            "prepare_rfq_handoff",
            return_value=prepared,
        ) as prepare:
            denied = self.client.post(
                f"/requests/{self.request_id}/rfq-handoff",
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            prepare.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/rfq-handoff",
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                prepare.call_args.kwargs["actor"],
                "operator:wasantha",
            )

        with patch.object(
            api,
            "get_rfq_for_request",
            return_value=prepared,
        ):
            readable = self.client.get(
                f"/requests/{self.request_id}/rfq-handoff",
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(readable.status_code, 200)

    def test_rfq_delivery_activation_requires_decide_permission(self):
        handoff_id = uuid4()
        authorized = {
            "handoff_id": str(handoff_id),
            "status": "authorized",
            "response_reliability_started": False,
        }
        delivered = {
            "handoff_id": str(handoff_id),
            "status": "delivered",
            "response_reliability_started": True,
        }

        with patch.object(api, "authorize_rfq_delivery", return_value=authorized) as authorize:
            denied = self.client.post(
                f"/requests/{self.request_id}/rfq-handoffs/{handoff_id}/authorize-delivery",
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            authorize.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/rfq-handoffs/{handoff_id}/authorize-delivery",
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)

        with patch.object(api, "confirm_rfq_delivery", return_value=delivered) as confirm:
            denied = self.client.post(
                f"/requests/{self.request_id}/rfq-handoffs/{handoff_id}/confirm-delivery",
                json={"response_deadline_at": "2026-10-03T12:00:00+00:00"},
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            confirm.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/rfq-handoffs/{handoff_id}/confirm-delivery",
                json={"response_deadline_at": "2026-10-03T12:00:00+00:00"},
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)

    def test_normalized_quote_write_requires_decide_permission(self):
        handoff_id = uuid4()
        payload = {
            "amount_minor": 125000,
            "currency": "AUD",
            "scope_summary": "Replace leaking kitchen tap",
            "exclusions": [],
            "terms": [],
        }
        result = {
            "normalized_quote_id": str(uuid4()),
            "handoff_id": str(handoff_id),
            "amount_minor": 125000,
            "currency": "AUD",
            "evaluated": False,
            "selected": False,
        }

        with patch.object(
            api,
            "normalize_structured_quote",
            return_value=result,
        ) as normalize:
            denied = self.client.post(
                f"/requests/{self.request_id}/rfq-handoffs/{handoff_id}/normalized-quote",
                json=payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            normalize.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/rfq-handoffs/{handoff_id}/normalized-quote",
                json=payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                normalize.call_args.kwargs["actor"],
                "operator:wasantha",
            )

    def test_quote_completeness_requires_read_permission(self):
        handoff_id = uuid4()
        result = {
            "normalized_quote_id": str(uuid4()),
            "status": "complete",
            "comparison_ready": True,
            "requires_human_review": False,
        }

        with patch.object(
            api,
            "assess_quote_completeness",
            return_value=result,
        ) as assess:
            missing = self.client.get(
                f"/requests/{self.request_id}/rfq-handoffs/{handoff_id}/quote-completeness"
            )
            self.assertIn(missing.status_code, (401, 403))
            assess.assert_not_called()

            readable = self.client.get(
                f"/requests/{self.request_id}/rfq-handoffs/{handoff_id}/quote-completeness",
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(readable.status_code, 200)

    def test_quote_comparison_requires_read_permission(self):
        result = {
            "request_id": str(self.request_id),
            "status": "comparison_available",
            "quote_count": 2,
            "overall_winner_quote_id": None,
            "recommended_quote_id": None,
            "selected_quote_id": None,
        }

        with patch.object(
            api,
            "compare_request_quotes",
            return_value=result,
        ) as compare:
            missing = self.client.get(
                f"/requests/{self.request_id}/quote-comparison"
            )
            self.assertIn(missing.status_code, (401, 403))
            compare.assert_not_called()

            readable = self.client.get(
                f"/requests/{self.request_id}/quote-comparison",
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(readable.status_code, 200)

    def test_quote_recommendation_requires_decide_permission(self):
        quote_id = uuid4()
        payload = {
            "normalized_quote_id": str(quote_id),
            "rationale": "Human review preferred this quote",
        }
        result = {
            "recommendation_id": str(uuid4()),
            "request_id": str(self.request_id),
            "normalized_quote_id": str(quote_id),
            "recommendation_authority": "human",
            "award_created": False,
            "provider_contacted": False,
        }

        with patch.object(
            api,
            "recommend_quote_for_request",
            return_value=result,
        ) as recommend:
            denied = self.client.post(
                f"/requests/{self.request_id}/quote-recommendation",
                json=payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            recommend.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/quote-recommendation",
                json=payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                recommend.call_args.kwargs["actor"],
                "operator:wasantha",
            )

    def test_quote_award_requires_decide_permission(self):
        recommendation_id = uuid4()
        payload = {
            "recommendation_id": str(recommendation_id),
            "reason": "Human confirmed award",
        }
        result = {
            "award_id": str(uuid4()),
            "request_id": str(self.request_id),
            "recommendation_id": str(recommendation_id),
            "award_authority": "human",
            "provider_contacted": False,
            "dispatch_created": False,
            "request_status_changed": False,
        }

        with patch.object(
            api,
            "award_recommended_quote",
            return_value=result,
        ) as award:
            denied = self.client.post(
                f"/requests/{self.request_id}/quote-award",
                json=payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            award.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/quote-award",
                json=payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                award.call_args.kwargs["actor"],
                "operator:wasantha",
            )

    def test_delivery_handoff_requires_decide_permission(self):
        award_id = uuid4()
        payload = {"award_id": str(award_id)}
        result = {
            "delivery_handoff_id": str(uuid4()),
            "request_id": str(self.request_id),
            "award_id": str(award_id),
            "request_status": "actioned",
            "provider_contacted": False,
            "dispatch_created": False,
            "appointment_created": False,
        }

        with patch.object(
            api,
            "activate_delivery_handoff",
            return_value=result,
        ) as activate:
            denied = self.client.post(
                f"/requests/{self.request_id}/delivery-handoff",
                json=payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            activate.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/delivery-handoff",
                json=payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                activate.call_args.kwargs["actor"],
                "operator:wasantha",
            )

    def test_delivery_notification_preparation_requires_decide_permission(self):
        result = {
            "request_id": str(self.request_id),
            "delivery_handoff_id": str(uuid4()),
            "notifications": [],
            "destinations_resolved": False,
            "sent": False,
        }

        with patch.object(
            api,
            "prepare_delivery_notifications",
            return_value=result,
        ) as prepare:
            denied = self.client.post(
                f"/requests/{self.request_id}/delivery-notifications",
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            prepare.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/delivery-notifications",
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                prepare.call_args.kwargs["actor"],
                "operator:wasantha",
            )

    def test_delivery_appointment_actions_require_decide_permission(self):
        appointment_id = uuid4()
        proposal_payload = {
            "proposed_start_at": "2027-01-01T10:00:00Z",
            "proposed_end_at": "2027-01-01T12:00:00Z",
            "reason": "Human proposed a service window",
        }
        confirmation_payload = {
            "appointment_id": str(appointment_id),
            "reason": "Human confirmed the service window",
        }

        proposal_result = {
            "appointment_id": str(appointment_id),
            "request_id": str(self.request_id),
            "status": "proposed",
        }
        confirmation_result = {
            "appointment_id": str(appointment_id),
            "request_id": str(self.request_id),
            "status": "confirmed",
        }

        with patch.object(
            api,
            "propose_delivery_appointment",
            return_value=proposal_result,
        ) as propose:
            denied = self.client.post(
                f"/requests/{self.request_id}/delivery-appointment/proposal",
                json=proposal_payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            propose.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/delivery-appointment/proposal",
                json=proposal_payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                propose.call_args.kwargs["actor"],
                "operator:wasantha",
            )

        with patch.object(
            api,
            "confirm_delivery_appointment",
            return_value=confirmation_result,
        ) as confirm:
            denied = self.client.post(
                f"/requests/{self.request_id}/delivery-appointment/confirmation",
                json=confirmation_payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            confirm.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/delivery-appointment/confirmation",
                json=confirmation_payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                confirm.call_args.kwargs["actor"],
                "operator:wasantha",
            )

    def test_delivery_status_actions_require_decide_permission(self):
        appointment_id = uuid4()
        delivery_status_id = uuid4()

        schedule_payload = {
            "appointment_id": str(appointment_id),
            "reason": "Human scheduled service delivery",
        }
        start_payload = {
            "delivery_status_id": str(delivery_status_id),
            "reason": "Human confirmed work has started",
        }

        schedule_result = {
            "delivery_status_id": str(delivery_status_id),
            "request_id": str(self.request_id),
            "status": "scheduled",
        }
        start_result = {
            "delivery_status_id": str(delivery_status_id),
            "request_id": str(self.request_id),
            "status": "in_progress",
        }

        with patch.object(
            api,
            "initialize_delivery_status",
            return_value=schedule_result,
        ) as schedule:
            denied = self.client.post(
                f"/requests/{self.request_id}/delivery-status/schedule",
                json=schedule_payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            schedule.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/delivery-status/schedule",
                json=schedule_payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                schedule.call_args.kwargs["actor"],
                "operator:wasantha",
            )

        with patch.object(
            api,
            "start_delivery",
            return_value=start_result,
        ) as start:
            denied = self.client.post(
                f"/requests/{self.request_id}/delivery-status/start",
                json=start_payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            start.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/delivery-status/start",
                json=start_payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                start.call_args.kwargs["actor"],
                "operator:wasantha",
            )

    def test_service_completion_requires_decide_permission(self):
        delivery_status_id = uuid4()
        payload = {
            "delivery_status_id": str(delivery_status_id),
            "reason": "Human confirmed service completion",
        }
        result = {
            "delivery_status_id": str(delivery_status_id),
            "request_id": str(self.request_id),
            "status": "completed",
        }

        with patch.object(
            api,
            "complete_delivery",
            return_value=result,
        ) as complete:
            denied = self.client.post(
                f"/requests/{self.request_id}/delivery-status/complete",
                json=payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            complete.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/delivery-status/complete",
                json=payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                complete.call_args.kwargs["actor"],
                "operator:wasantha",
            )

    def test_delivery_exception_write_requires_decide_permission(self):
        exception_id = uuid4()
        delivery_status_id = uuid4()
        payload = {
            "exception_id": str(exception_id),
            "delivery_status_id": str(delivery_status_id),
            "exception_kind": "delay",
            "occurred_at": "2026-10-05T03:00:00Z",
            "summary": "Provider reported a delay",
            "expected_resolution_at": "2026-10-05T04:00:00Z",
        }
        result = {
            "exception_id": str(exception_id),
            "request_id": str(self.request_id),
            "exception_kind": "delay",
        }

        with patch.object(
            api,
            "record_delivery_exception",
            return_value=result,
        ) as record:
            denied = self.client.post(
                f"/requests/{self.request_id}/delivery-exceptions",
                json=payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            record.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/delivery-exceptions",
                json=payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                record.call_args.kwargs["actor"],
                "operator:wasantha",
            )

    def test_human_intervention_actions_require_decide_permission(self):
        exception_id = uuid4()
        intervention_id = uuid4()

        create_payload = {
            "exception_id": str(exception_id),
            "priority": "high",
            "reason": "Operator attention required",
        }
        acknowledge_payload = {
            "intervention_id": str(intervention_id),
            "reason": "Operator acknowledged intervention",
        }

        create_result = {
            "intervention_id": str(intervention_id),
            "request_id": str(self.request_id),
            "status": "open",
        }
        acknowledge_result = {
            "intervention_id": str(intervention_id),
            "request_id": str(self.request_id),
            "status": "acknowledged",
        }

        with patch.object(
            api,
            "create_human_intervention",
            return_value=create_result,
        ) as create:
            denied = self.client.post(
                f"/requests/{self.request_id}/human-interventions",
                json=create_payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            create.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/human-interventions",
                json=create_payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                create.call_args.kwargs["actor"],
                "operator:wasantha",
            )

        with patch.object(
            api,
            "acknowledge_human_intervention",
            return_value=acknowledge_result,
        ) as acknowledge:
            denied = self.client.post(
                f"/requests/{self.request_id}/human-interventions/acknowledge",
                json=acknowledge_payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            acknowledge.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/human-interventions/acknowledge",
                json=acknowledge_payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                acknowledge.call_args.kwargs["actor"],
                "operator:wasantha",
            )

    def test_delivery_timeline_requires_read_permission(self):
        result = {
            "request_id": str(self.request_id),
            "event_count": 0,
            "latest_stage": None,
            "delivery_completed": False,
            "has_exceptions": False,
            "has_interventions": False,
            "timeline": [],
        }

        with (
            patch.object(
                api,
                "get_request",
                return_value={"id": self.request_id},
            ),
            patch.object(
                api,
                "get_delivery_timeline",
                return_value=result,
            ) as timeline,
        ):
            denied = self.client.get(
                f"/requests/{self.request_id}/delivery-timeline",
            )
            self.assertEqual(denied.status_code, 401)
            timeline.assert_not_called()

            allowed = self.client.get(
                f"/requests/{self.request_id}/delivery-timeline",
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            timeline.assert_called_once_with(self.request_id)

    def test_satisfaction_follow_up_permissions(self):
        result = {
            "follow_up_id": str(uuid4()),
            "request_id": str(self.request_id),
            "status": "prepared",
        }

        with patch.object(
            api,
            "prepare_satisfaction_follow_up",
            return_value=result,
        ) as prepare:
            denied = self.client.post(
                f"/requests/{self.request_id}/satisfaction-follow-up",
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            prepare.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/satisfaction-follow-up",
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                prepare.call_args.kwargs["actor"],
                "operator:wasantha",
            )

        with (
            patch.object(
                api,
                "get_satisfaction_follow_up",
                return_value=result,
            ) as retrieve,
        ):
            allowed = self.client.get(
                f"/requests/{self.request_id}/satisfaction-follow-up",
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            retrieve.assert_called_once_with(self.request_id)

    def test_satisfaction_response_requires_decide_permission(self):
        follow_up_id = uuid4()
        payload = {
            "follow_up_id": str(follow_up_id),
            "rating": 4,
            "responded_at": "2026-10-05T05:00:00Z",
            "response_source": "phone",
            "comment": "Good service",
        }
        result = {
            "follow_up_id": str(follow_up_id),
            "request_id": str(self.request_id),
            "status": "responded",
            "rating": 4,
        }

        with patch.object(
            api,
            "record_satisfaction_response",
            return_value=result,
        ) as record:
            denied = self.client.post(
                f"/requests/{self.request_id}/satisfaction-follow-up/response",
                json=payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            record.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/satisfaction-follow-up/response",
                json=payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                record.call_args.kwargs["actor"],
                "operator:wasantha",
            )

    def test_review_request_permissions(self):
        follow_up_id = uuid4()
        review_request_id = uuid4()
        payload = {
            "satisfaction_follow_up_id": str(follow_up_id),
            "reason": "Operator approved review request preparation",
        }
        result = {
            "review_request_id": str(review_request_id),
            "request_id": str(self.request_id),
            "status": "prepared",
        }

        with patch.object(
            api,
            "prepare_review_request",
            return_value=result,
        ) as prepare:
            denied = self.client.post(
                f"/requests/{self.request_id}/review-request",
                json=payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            prepare.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/review-request",
                json=payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                prepare.call_args.kwargs["actor"],
                "operator:wasantha",
            )

        with patch.object(
            api,
            "get_review_request",
            return_value=result,
        ) as retrieve:
            allowed = self.client.get(
                f"/requests/{self.request_id}/review-request",
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            retrieve.assert_called_once_with(self.request_id)

    def test_closure_escalation_permissions(self):
        follow_up_id = uuid4()
        escalation_id = uuid4()
        payload = {
            "satisfaction_follow_up_id": str(follow_up_id),
            "escalation_kind": "complaint",
            "priority": "high",
            "reason": "Customer complaint requires review",
        }
        result = {
            "escalation_id": str(escalation_id),
            "request_id": str(self.request_id),
            "status": "open",
            "escalation_kind": "complaint",
        }

        with patch.object(
            api,
            "create_closure_escalation",
            return_value=result,
        ) as create:
            denied = self.client.post(
                f"/requests/{self.request_id}/closure-escalations",
                json=payload,
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(denied.status_code, 403)
            create.assert_not_called()

            allowed = self.client.post(
                f"/requests/{self.request_id}/closure-escalations",
                json=payload,
                headers={"X-API-Key": OPERATOR_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(
                create.call_args.kwargs["actor"],
                "operator:wasantha",
            )

        with patch.object(
            api,
            "get_closure_escalations",
            return_value=[result],
        ) as retrieve:
            allowed = self.client.get(
                f"/requests/{self.request_id}/closure-escalations",
                headers={"X-API-Key": VIEWER_KEY},
            )
            self.assertEqual(allowed.status_code, 200)
            retrieve.assert_called_once_with(self.request_id)

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
            ("GET", f"/requests/{self.request_id}/provider-selection", None, OPERATOR_KEY, INBOUND_KEY),
            ("POST", f"/requests/{self.request_id}/provider-selection", {
                "service_slug": "plumbing",
                "area_key": "bn:brunei-muara",
                "provider_ids": [str(uuid4())],
            }, OPERATOR_KEY, INBOUND_KEY),
            ("GET", f"/requests/{self.request_id}/rfq-handoff", None, OPERATOR_KEY, INBOUND_KEY),
            ("POST", f"/requests/{self.request_id}/rfq-handoff", None, OPERATOR_KEY, INBOUND_KEY),
            ("POST", f"/requests/{self.request_id}/tools/prepare_customer_follow_up", None, OPERATOR_KEY, INBOUND_KEY),
        ]
        for method, path, body, correct, wrong in paths:
            with self.subTest(path=path):
                for key in (None, wrong, "invalid-" + "z" * 40):
                    headers = {"X-API-Key": key} if key else {}
                    response = self.client.request(method, path, json=body, headers=headers)
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.json(), {"detail": "Invalid API credentials"})

                if "/provider-selection" in path:
                    if method == "GET":
                        context = patch.object(
                            api,
                            "get_provider_selection",
                            return_value=None,
                        )
                    else:
                        context = patch.object(
                            api,
                            "select_providers_for_request",
                            side_effect=api.ProviderSelectionNotFoundError(
                                "Request not found"
                            ),
                        )
                    with context:
                        response = self.client.request(
                            method,
                            path,
                            json=body,
                            headers={"X-API-Key": correct},
                        )
                    self.assertEqual(response.status_code, 404)
                elif "/rfq-handoff" in path:
                    if method == "GET":
                        context = patch.object(
                            api,
                            "get_rfq_for_request",
                            return_value=None,
                        )
                    else:
                        context = patch.object(
                            api,
                            "prepare_rfq_handoff",
                            side_effect=api.RFQHandoffNotFoundError(
                                "Request not found"
                            ),
                        )
                    with context:
                        response = self.client.request(
                            method,
                            path,
                            json=body,
                            headers={"X-API-Key": correct},
                        )
                    self.assertEqual(response.status_code, 404)
                elif path.startswith("/requests/") or path.endswith("/reply"):
                    with patch.object(api, "get_request", return_value=None):
                        response = self.client.request(
                            method,
                            path,
                            json=body,
                            headers={"X-API-Key": correct},
                        )
                    self.assertEqual(response.status_code, 404)

    def test_inbound_credential_can_create_request(self):
        analysis = {"category": "plumbing"}
        with patch.object(api, "save_inbound_message", return_value=inbound_persistence_result()), \
             patch.object(api, "link_inbound_message_to_request"), \
             patch.object(api, "analyze_quote_request", return_value=analysis), \
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
        request = {
            "source": "website",
            "status": "needs_information",
            "message": "Test",
            "customer_name": "Test",
        }
        with patch.object(api, "get_request", return_value=request):
            paths = [
                ("POST", "/agent", {"message": "Test"}),
                ("POST", f"/requests/{self.request_id}/reply", {"message": "Test"}),
                ("POST", f"/requests/{self.request_id}/approve", {}),
                ("POST", f"/requests/{self.request_id}/reject", {}),
                ("POST", f"/requests/{self.request_id}/tools/prepare_customer_follow_up", None),
            ]
            for method, path, body in paths:
                with self.subTest(path=path):
                    response = self.client.request(
                        method,
                        path,
                        json=body,
                        headers={"X-API-Key": VIEWER_KEY},
                    )
                    self.assertEqual(response.status_code, 403)

    def test_owned_request_read_succeeds_for_authorized_operator(self):
        stored = {
            "id": self.request_id,
            "source": "website",
            "customer_name": "Test",
            "message": "Test",
            "status": "ready",
        }
        with patch.object(api, "get_request", return_value=stored):
            response = self.client.get(
                f"/requests/{self.request_id}",
                headers={"X-API-Key": OPERATOR_KEY},
            )
        self.assertEqual(response.status_code, 200)

    def test_operator_tools_require_allowed_state(self):
        stored = {
            "id": self.request_id,
            "source": "website",
            "status": "ready",
        }
        with patch.object(api, "get_request", return_value=stored):
            response = self.client.post(
                f"/requests/{self.request_id}/tools/prepare_customer_follow_up",
                headers={"X-API-Key": OPERATOR_KEY},
            )
        self.assertEqual(response.status_code, 409)

    def test_operator_tool_executes_when_authorized_and_allowed(self):
        stored = {
            "id": self.request_id,
            "source": "website",
            "status": "needs_information",
            "follow_up_questions": ["Where is the leak?"],
        }
        with patch.object(api, "get_request", return_value=stored), \
             patch.object(api, "record_event") as event, \
             patch.object(api, "execute_tool", return_value={"message": "Please provide details"}):
            response = self.client.post(
                f"/requests/{self.request_id}/tools/prepare_customer_follow_up",
                headers={"X-API-Key": OPERATOR_KEY},
            )
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(event.call_count, 2)

    def test_operator_tool_failure_is_audited(self):
        stored = {
            "id": self.request_id,
            "source": "website",
            "status": "needs_information",
            "follow_up_questions": ["Where is the leak?"],
        }
        with patch.object(api, "get_request", return_value=stored), \
             patch.object(api, "record_event") as event, \
             patch.object(api, "execute_tool", side_effect=ToolExecutionError("bad")):
            response = self.client.post(
                f"/requests/{self.request_id}/tools/prepare_customer_follow_up",
                headers={"X-API-Key": OPERATOR_KEY},
            )
        self.assertEqual(response.status_code, 422)
        self.assertGreaterEqual(event.call_count, 2)


if __name__ == "__main__":
    unittest.main()
