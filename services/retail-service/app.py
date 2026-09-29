import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


SERVICE = os.getenv("SERVICE_NAME", "retail-service")
PORT = int(os.getenv("PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    def _write(self, status, body):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/health":
            return self._write(200, {"status": "ok", "service": SERVICE})
        if self.path == "/ready":
            return self._write(200, {"status": "ready", "service": SERVICE})
        return self._write(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/orders" or SERVICE != "order-service":
            return self._write(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        order_id = str(uuid.uuid4())
        return self._write(201, {
            "orderId": order_id,
            "status": "PENDING",
            "items": body.get("items", []),
            "event": "OrderCreated",
        })

    def log_message(self, fmt, *args):
        print(f"[{SERVICE}] {fmt % args}")


if __name__ == "__main__":
    print(f"Starting {SERVICE} on port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
