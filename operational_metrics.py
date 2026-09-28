"""Privacy-safe in-process operational metrics for the single agent process."""

import threading
import time
from collections import Counter


class OperationalMetrics:
    """Aggregate bounded HTTP metrics without request or identity data."""

    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self.started_at = self.clock()
        self._lock = threading.Lock()
        self._requests_total = 0
        self._exceptions_total = 0
        self._duration_ms_total = 0.0
        self._duration_ms_max = 0.0
        self._status_codes = Counter()
        self._status_classes = Counter()
        self._methods = Counter()
        self._routes = Counter()
        self._request_size_rejections_total = 0
        self._rate_limit_rejections_total = 0

    @staticmethod
    def _safe_method(method):
        return method if method else "UNKNOWN"

    @staticmethod
    def _safe_route(route):
        return route if route else "<unresolved>"

    def _record_common(self, method, route, duration_ms):
        self._requests_total += 1
        self._duration_ms_total += float(duration_ms)
        self._duration_ms_max = max(self._duration_ms_max, float(duration_ms))
        self._methods[self._safe_method(method)] += 1
        self._routes[self._safe_route(route)] += 1

    def record_completed(self, method, route, status_code, duration_ms):
        with self._lock:
            self._record_common(method, route, duration_ms)
            if status_code is not None:
                code = int(status_code)
                self._status_codes[str(code)] += 1
                self._status_classes[f"{code // 100}xx"] += 1
                if code == 413:
                    self._request_size_rejections_total += 1
                elif code == 429:
                    self._rate_limit_rejections_total += 1

    def record_exception(self, method, route, duration_ms):
        with self._lock:
            self._record_common(method, route, duration_ms)
            self._exceptions_total += 1

    def snapshot(self):
        with self._lock:
            return {
                "process": {
                    "uptime_seconds": round(max(0.0, self.clock() - self.started_at), 2),
                },
                "http": {
                    "requests_total": self._requests_total,
                    "exceptions_total": self._exceptions_total,
                    "duration_ms_total": round(self._duration_ms_total, 2),
                    "duration_ms_max": round(self._duration_ms_max, 2),
                    "status_codes": dict(sorted(self._status_codes.items())),
                    "status_classes": dict(sorted(self._status_classes.items())),
                    "methods": dict(sorted(self._methods.items())),
                    "routes": dict(sorted(self._routes.items())),
                    "request_size_rejections_total": self._request_size_rejections_total,
                    "rate_limit_rejections_total": self._rate_limit_rejections_total,
                },
            }


operational_metrics = OperationalMetrics()
