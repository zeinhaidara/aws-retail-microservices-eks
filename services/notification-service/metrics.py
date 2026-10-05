"""Small, thread-safe Prometheus collector. No request bodies or recipient labels."""
import threading
import time
from collections import Counter
from functools import wraps
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

LOCK = threading.Lock()
REQUESTS = Counter()
EVENTS = Counter()
BUCKETS = (0.005, 0.025, 0.1, 0.5, 1, 5, 30, float("inf"))
DURATION_BUCKETS = Counter()
DURATION_SUM = 0.0
DURATION_COUNT = 0
EVENT_NAMES = ("orders_confirmed", "email_sent", "email_failed", "outbox_published", "outbox_failed")


def event(name):
    if name not in EVENT_NAMES:
        raise ValueError("Unknown metric event")
    with LOCK:
        EVENTS[name] += 1


def exposition():
    with LOCK:
        lines = ["# HELP retail_http_requests_total Completed non-probe HTTP requests.",
                 "# TYPE retail_http_requests_total counter"]
        for (method, status), count in sorted(REQUESTS.items()):
            lines.append(f'retail_http_requests_total{{method="{method}",status="{status}"}} {count}')
        lines.append("# HELP retail_http_request_duration_seconds Non-probe HTTP request duration.")
        lines.append("# TYPE retail_http_request_duration_seconds histogram")
        for bucket in BUCKETS:
            bound = "+Inf" if bucket == float("inf") else str(bucket)
            lines.append(f'retail_http_request_duration_seconds_bucket{{le="{bound}"}} {DURATION_BUCKETS[bucket]}')
        lines.extend([
            f"retail_http_request_duration_seconds_sum {DURATION_SUM}",
            f"retail_http_request_duration_seconds_count {DURATION_COUNT}",
            "# HELP retail_events_total Business processing events and attempts.",
            "# TYPE retail_events_total counter",
        ])
        for name in EVENT_NAMES:
            lines.append(f'retail_events_total{{event="{name}"}} {EVENTS[name]}')
        return ("\n".join(lines) + "\n").encode()


class MetricsHandler(BaseHTTPRequestHandler):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        original = cls.do_GET
        @wraps(original)
        def get(self):
            if urlparse(self.path).path != "/metrics":
                return original(self)
            body = exposition()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        cls.do_GET = get

    def handle_one_request(self):
        global DURATION_SUM, DURATION_COUNT
        started = time.monotonic()
        self._metric_status = None
        try:
            super().handle_one_request()
        finally:
            path = urlparse(getattr(self, "path", "")).path
            if self._metric_status is not None and path not in ("/health", "/ready", "/metrics"):
                elapsed = time.monotonic() - started
                method = self.command if self.command in ("GET", "POST", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS") else "OTHER"
                with LOCK:
                    REQUESTS[(method, self._metric_status)] += 1
                    DURATION_SUM += elapsed
                    DURATION_COUNT += 1
                    for bucket in BUCKETS:
                        DURATION_BUCKETS[bucket] += elapsed <= bucket

    def send_response(self, code, message=None):
        self._metric_status = code
        super().send_response(code, message)

    def log_message(self, fmt, *args):
        # Routine access/probe logs are intentionally disabled.
        pass
