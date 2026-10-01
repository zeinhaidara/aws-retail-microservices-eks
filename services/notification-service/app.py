import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SERVICE = "notification-service"
PORT = int(os.getenv("PORT", "8080"))
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8080")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8080")

ORDERS = {}
ORDERS_LOCK = threading.Lock()


def json_request(url, method="GET", body=None):
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(url, data=payload, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read() or b"{}")


class Handler(BaseHTTPRequestHandler):
    def _write(self, status, body):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return None

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"

        if path == "/health":
            return self._write(200, {"status": "ok", "service": SERVICE})
        if path == "/ready":
            return self._write(200, {"status": "ready", "service": SERVICE})

        if SERVICE == "product-service" and path == "/products":
            return self._write(200, {"items": list(PRODUCTS.values())})
        if SERVICE == "product-service" and path.startswith("/products/"):
            product = PRODUCTS.get(path.split("/")[-1])
            return self._write(200, product) if product else self._write(404, {"error": "product not found"})

        if SERVICE == "inventory-service" and path.startswith("/inventory/"):
            product_id = path.split("/")[-1]
            if product_id not in INVENTORY:
                return self._write(404, {"error": "inventory not found"})
            return self._write(200, {"productId": product_id, "available": INVENTORY[product_id]})
        if SERVICE == "inventory-service" and path == "/inventory":
            with INVENTORY_LOCK:
                items = [
                    {"productId": product_id, "available": available}
                    for product_id, available in INVENTORY.items()
                ]
            return self._write(200, {"items": items})

        if SERVICE == "order-service" and path.startswith("/orders/"):
            with ORDERS_LOCK:
                order = ORDERS.get(path.split("/")[-1])
            return self._write(200, order) if order else self._write(404, {"error": "order not found"})

        return self._write(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        body = self._read_body()
        if body is None:
            return self._write(400, {"error": "invalid JSON body"})

        if SERVICE == "inventory-service" and path == "/inventory/reservations":
            if not isinstance(body, dict):
                return self._write(400, {"error": "request body must be an object"})
            items = body.get("items", [])
            if not items:
                return self._write(400, {"error": "items are required"})
            if not isinstance(items, list):
                return self._write(400, {"error": "items must be a list"})
            requested = {}
            for item in items:
                if not isinstance(item, dict):
                    return self._write(400, {"error": "invalid inventory item"})
                product_id = item.get("productId")
                quantity = item.get("quantity", 0)
                if product_id not in INVENTORY or type(quantity) is not int or quantity < 1:
                    return self._write(400, {"error": "invalid inventory item"})
                requested[product_id] = requested.get(product_id, 0) + quantity
            with INVENTORY_LOCK:
                for product_id, quantity in requested.items():
                    if INVENTORY[product_id] < quantity:
                        return self._write(409, {"error": "insufficient inventory", "productId": product_id})
                for product_id, quantity in requested.items():
                    INVENTORY[product_id] -= quantity
            reserved = [{"productId": product_id, "quantity": quantity} for product_id, quantity in requested.items()]
            return self._write(201, {"status": "RESERVED", "items": reserved, "event": "InventoryReserved"})

        if SERVICE == "order-service" and path == "/orders":
            if not isinstance(body, dict):
                return self._write(400, {"error": "request body must be an object"})
            items = body.get("items", [])
            if not isinstance(items, list) or not items:
                return self._write(400, {"error": "items are required"})

            try:
                requested = {}
                for item in items:
                    if not isinstance(item, dict):
                        return self._write(400, {"error": "invalid order item"})
                    product_id = item.get("productId")
                    quantity = item.get("quantity", 0)
                    if not isinstance(product_id, str) or type(quantity) is not int or quantity < 1:
                        return self._write(400, {"error": "quantity must be a positive integer"})
                    requested[product_id] = requested.get(product_id, 0) + quantity

                product_items = []
                total = 0.0
                normalized_items = [{"productId": product_id, "quantity": quantity} for product_id, quantity in requested.items()]
                for item in normalized_items:
                    product_id = item["productId"]
                    quantity = item["quantity"]
                    _, product = json_request(f"{PRODUCT_SERVICE_URL}/products/{product_id}")
                    line_total = round(product["price"] * quantity, 2)
                    total += line_total
                    product_items.append({**item, "name": product["name"], "unitPrice": product["price"], "lineTotal": line_total})
                _, inventory = json_request(
                    f"{INVENTORY_SERVICE_URL}/inventory/reservations", method="POST", body={"items": normalized_items}
                )
            except HTTPError as error:
                details = json.loads(error.read() or b"{}")
                return self._write(error.code, details)
            except (URLError, TimeoutError):
                return self._write(503, {"error": "dependent service unavailable"})

            order_id = str(uuid.uuid4())
            order = {
                "orderId": order_id,
                "status": "CONFIRMED",
                "items": product_items,
                "total": round(total, 2),
                "inventory": inventory,
                "event": "OrderCreated",
            }
            with ORDERS_LOCK:
                ORDERS[order_id] = order
            return self._write(201, order)

        return self._write(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        print(f"[{SERVICE}] {fmt % args}")


if __name__ == "__main__":
    print(f"Starting {SERVICE} on port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
