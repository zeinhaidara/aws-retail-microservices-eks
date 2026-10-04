import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8080")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8080")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8080")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8080")
TRIP_PLANNER_URL = os.getenv("TRIP_PLANNER_URL", "http://trip-planner:8080")
ASSETS = {"backpack.jpg", "bottle.jpg", "hoodie.jpg", "orbital-hero-v2.png"}


def json_request(url, method="GET", body=None):
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(url, data=payload, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read() or b"{}")


class Handler(BaseHTTPRequestHandler):
    def _respond(self, status, body, content_type="application/json"):
        payload = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _proxy(self, base_url, path, method="GET", body=None):
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            f"{base_url}{path}",
            data=payload,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            timeout = 35 if base_url == TRIP_PLANNER_URL else 5
            with urlopen(request, timeout=timeout) as response:
                self._respond(response.status, response.read())
        except HTTPError as error:
            self._respond(error.code, error.read())
        except (URLError, TimeoutError):
            self._respond(503, {"error": "backend service unavailable"})

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 16384:
                return None
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return None

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open("index.html", "rb") as page:
                return self._respond(200, page.read(), "text/html; charset=utf-8")
        if path.startswith("/assets/"):
            asset_name = path.removeprefix("/assets/")
            if asset_name not in ASSETS:
                return self._respond(404, {"error": "not found"})
            try:
                with open(f"assets/{asset_name}", "rb") as asset:
                    content_type = "image/png" if asset_name.endswith(".png") else "image/jpeg"
                    return self._respond(200, asset.read(), content_type)
            except FileNotFoundError:
                return self._respond(404, {"error": "asset not found"})
        if path == "/health" or path == "/ready":
            return self._respond(200, {"status": "ok", "service": "storefront"})
        if path == "/api/products":
            return self._proxy(PRODUCT_SERVICE_URL, "/products")
        if path == "/api/inventory":
            return self._proxy(INVENTORY_SERVICE_URL, "/inventory")
        return self._respond(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/orders", "/api/trip-plan", "/api/chat", "/api/email/verify", "/api/email/status"):
            return self._respond(404, {"error": "not found"})
        body = self._read_json()
        if not isinstance(body, dict):
            return self._respond(400, {"error": "invalid JSON body"})
        if path == "/api/orders":
            return self._proxy(ORDER_SERVICE_URL, "/orders", method="POST", body=body)
        if path.startswith("/api/email/"):
            return self._proxy(NOTIFICATION_SERVICE_URL, path.removeprefix("/api"), method="POST", body=body)
        return self._proxy(TRIP_PLANNER_URL, "/chat" if path == "/api/chat" else "/trip-plan", method="POST", body=body)

    def log_message(self, fmt, *args):
        print(f"[storefront] {fmt % args}")


if __name__ == "__main__":
    print("Starting storefront on port 8080")
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
