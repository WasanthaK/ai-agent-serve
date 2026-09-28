import importlib
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from operational_metrics import OperationalMetrics


INBOUND_KEY = "inbound-" + "a" * 40
OPERATOR_KEY = "operator-" + "b" * 40
OPERATORS = [
    {"id": "wasantha", "key": OPERATOR_KEY,
     "permissions": ["read", "analyze", "reply", "decide", "tools"]},
]

with patch.dict(os.environ, {
    "OPENAI_API_KEY": "test-only-key",
    "AGENT_INBOUND_API_KEY": INBOUND_KEY,
    "AGENT_OPERATOR_CREDENTIALS": json.dumps(OPERATORS),
    "AGENT_INBOUND_SOURCE": "website",
}):
    api = importlib.import_module("app")


class FakeClock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


class ModelCallMetricsTests(unittest.TestCase):
    def test_measure_model_call_records_success_and_latency(self):
        clock = FakeClock(10.0)
        metrics = OperationalMetrics(clock=clock)

        def call():
            clock.value = 10.125
            return "ok"

        self.assertEqual(metrics.measure_model_call(call), "ok")
        model = metrics.snapshot()["model_calls"]
        self.assertEqual(model["calls_total"], 1)
        self.assertEqual(model["successes_total"], 1)
        self.assertEqual(model["failures_total"], 0)
        self.assertEqual(model["latency_ms_total"], 125.0)
        self.assertEqual(model["latency_ms_average"], 125.0)
        self.assertEqual(model["latency_ms_max"], 125.0)

    def test_measure_model_call_records_failure_and_reraises(self):
        clock = FakeClock(5.0)
        metrics = OperationalMetrics(clock=clock)
        secret = "private-provider-error-marker"

        def call():
            clock.value = 5.05
            raise RuntimeError(secret)

        with self.assertRaisesRegex(RuntimeError, secret):
            metrics.measure_model_call(call)

        snapshot = metrics.snapshot()
        model = snapshot["model_calls"]
        self.assertEqual(model["calls_total"], 1)
        self.assertEqual(model["successes_total"], 0)
        self.assertEqual(model["failures_total"], 1)
        self.assertEqual(model["latency_ms_total"], 50.0)
        self.assertNotIn(secret, str(snapshot))

    def test_analyze_quote_request_uses_measured_model_boundary(self):
        parsed = {"intent": "quote"}
        response = SimpleNamespace(output_text=json.dumps(parsed))

        with patch.object(
            api.operational_metrics,
            "measure_model_call",
            side_effect=lambda call: call(),
        ) as measure, patch.object(
            api.client.responses,
            "create",
            return_value=response,
        ) as create:
            result = api.analyze_quote_request("Replace a tap")

        self.assertEqual(result, parsed)
        measure.assert_called_once()
        create.assert_called_once()

    def test_provider_failure_keeps_existing_502_contract(self):
        with patch.object(
            api.client.responses,
            "create",
            side_effect=RuntimeError("provider-secret-marker"),
        ):
            with self.assertRaises(HTTPException) as raised:
                api.analyze_quote_request("Replace a tap")

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(
            raised.exception.detail,
            "Request analysis is temporarily unavailable",
        )

    def test_invalid_json_is_provider_success_but_analysis_failure(self):
        metrics = OperationalMetrics()
        response = SimpleNamespace(output_text="not-valid-json")

        with patch.object(api, "operational_metrics", metrics), patch.object(
            api.client.responses,
            "create",
            return_value=response,
        ):
            with self.assertRaises(HTTPException) as raised:
                api.analyze_quote_request("Replace a tap")

        self.assertEqual(raised.exception.status_code, 502)
        model = metrics.snapshot()["model_calls"]
        self.assertEqual(model["calls_total"], 1)
        self.assertEqual(model["successes_total"], 1)
        self.assertEqual(model["failures_total"], 0)


if __name__ == "__main__":
    unittest.main()
