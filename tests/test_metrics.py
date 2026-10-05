import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVICES = ("product-service", "inventory-service", "order-service", "notification-service", "trip-planner", "storefront")

class MetricsTests(unittest.TestCase):
    def test_each_service_metrics(self):
        code = '''
import importlib, threading, time
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from urllib.error import HTTPError
import metrics
module = importlib.import_module(MODULE)
server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = f"http://127.0.0.1:{server.server_port}"
try:
    urlopen(base + "/health", timeout=5).close()
    try:
        urlopen(base + "/missing", timeout=5)
    except HTTPError as error:
        assert error.code == 404
        error.close()
    for _ in range(100):
        if metrics.DURATION_COUNT == 1:
            break
        time.sleep(0.01)
    with urlopen(base + "/metrics", timeout=5) as response:
        assert "text/plain" in response.headers["Content-Type"]
        body = response.read().decode()
    assert 'status="404"} 1' in body, body
    assert 'status="200"' not in body, body
    assert 'retail_http_request_duration_seconds_count 1' in body, body
    assert 'le="+Inf"} 1' in body, body
    metrics.event("email_sent")
    assert 'event="email_sent"} 1' in metrics.exposition().decode()
    try:
        metrics.event("recipient@example.com")
        raise AssertionError("Unbounded label accepted")
    except ValueError:
        pass
finally:
    server.shutdown()
    server.server_close()
    thread.join()
'''
        for service in SERVICES:
            with self.subTest(service=service):
                result = subprocess.run([sys.executable, "-c", code.replace("MODULE", repr("server" if service == "storefront" else "app"))], cwd=ROOT / "services" / service, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_copies_match(self):
        copies = [(ROOT / "services" / service / "metrics.py").read_bytes() for service in SERVICES]
        self.assertTrue(all(content == copies[0] for content in copies))

if __name__ == "__main__":
    unittest.main()
