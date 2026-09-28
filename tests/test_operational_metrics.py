import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

import observability
from operational_metrics import OperationalMetrics
from observability import StructuredRequestLoggingMiddleware


class FakeClock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


class OperationalMetricsTests(unittest.TestCase):
    def test_completed_requests_aggregate_status_method_route_and_duration(self):
        clock = FakeClock(10.0)
        metrics = OperationalMetrics(clock=clock)

        metrics.record_completed("GET", "/requests/{request_id}", 200, 12.5)
        metrics.record_completed("POST", "/agent", 429, 7.5)

        snapshot = metrics.snapshot()
        http = snapshot["http"]
        self.assertEqual(http["requests_total"], 2)
        self.assertEqual(http["exceptions_total"], 0)
        self.assertEqual(http["duration_ms_total"], 20.0)
        self.assertEqual(http["duration_ms_max"], 12.5)
        self.assertEqual(http["status_codes"], {"200": 1, "429": 1})
        self.assertEqual(http["status_classes"], {"2xx": 1, "4xx": 1})
        self.assertEqual(http["methods"], {"GET": 1, "POST": 1})
        self.assertEqual(
            http["routes"],
            {"/agent": 1, "/requests/{request_id}": 1},
        )
        self.assertEqual(http["rate_limit_rejections_total"], 1)

    def test_size_and_rate_rejections_have_separate_counters(self):
        metrics = OperationalMetrics(clock=FakeClock())
        metrics.record_completed("POST", None, 413, 1.0)
        metrics.record_completed("POST", "/agent", 429, 1.0)

        http = metrics.snapshot()["http"]
        self.assertEqual(http["request_size_rejections_total"], 1)
        self.assertEqual(http["rate_limit_rejections_total"], 1)
        self.assertEqual(http["routes"]["<unresolved>"], 1)

    def test_exception_is_counted_without_error_detail(self):
        metrics = OperationalMetrics(clock=FakeClock())
        metrics.record_exception("GET", "/explode", 3.25)

        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["http"]["requests_total"], 1)
        self.assertEqual(snapshot["http"]["exceptions_total"], 1)
        self.assertNotIn("error", str(snapshot).lower())

    def test_uptime_uses_process_clock(self):
        clock = FakeClock(100.0)
        metrics = OperationalMetrics(clock=clock)
        clock.value = 112.345

        self.assertEqual(metrics.snapshot()["process"]["uptime_seconds"], 12.34)

    def test_dynamic_urls_are_aggregated_by_route_template(self):
        metrics = OperationalMetrics()
        app = FastAPI()

        with patch.object(observability, "operational_metrics", metrics):
            app.add_middleware(StructuredRequestLoggingMiddleware)

            @app.get("/requests/{request_id}")
            async def request_probe(request_id: str):
                return {"request_id": request_id}

            client = TestClient(app)
            first_id = str(uuid4())
            second_id = str(uuid4())
            self.assertEqual(client.get(f"/requests/{first_id}").status_code, 200)
            self.assertEqual(client.get(f"/requests/{second_id}").status_code, 200)

        routes = metrics.snapshot()["http"]["routes"]
        self.assertEqual(routes, {"/requests/{request_id}": 2})
        self.assertNotIn(first_id, str(routes))
        self.assertNotIn(second_id, str(routes))

    def test_middleware_records_413_rejection(self):
        metrics = OperationalMetrics()
        app = FastAPI()

        with patch.object(observability, "operational_metrics", metrics), \
             patch.object(observability, "MAX_REQUEST_BYTES", 5):
            app.add_middleware(StructuredRequestLoggingMiddleware)

            @app.post("/probe")
            async def probe():
                return {"ok": True}

            response = TestClient(app).post("/probe", content=b"123456")

        self.assertEqual(response.status_code, 413)
        http = metrics.snapshot()["http"]
        self.assertEqual(http["requests_total"], 1)
        self.assertEqual(http["status_codes"], {"413": 1})
        self.assertEqual(http["request_size_rejections_total"], 1)


if __name__ == "__main__":
    unittest.main()
