import json
import os
import threading
import time
import uuid
from decimal import Decimal
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SERVICE = "order-service"
PORT = int(os.getenv("PORT", "8080"))
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8080")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8080")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8080")
MYSQL_HOST = os.getenv("MYSQL_HOST", "")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "retail")
MYSQL_SECRET_ARN = os.getenv("MYSQL_SECRET_ARN", "")
EVENT_BUS_NAME = os.getenv("EVENT_BUS_NAME", "")
ORDERS = {}
ORDERS_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def secret_manager_client():
    import boto3

    return boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION"))


@lru_cache(maxsize=1)
def events_client():
    import boto3

    return boto3.client("events", region_name=os.getenv("AWS_REGION"))


@lru_cache(maxsize=1)
def mysql_credentials():
    if not MYSQL_SECRET_ARN:
        return {}
    response = secret_manager_client().get_secret_value(SecretId=MYSQL_SECRET_ARN)
    return json.loads(response["SecretString"])


def json_request(url, method="GET", body=None):
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(url, data=payload, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read() or b"{}")


def database_connection():
    import pymysql

    secret = mysql_credentials()
    return pymysql.connect(
        host=MYSQL_HOST or secret["host"],
        port=MYSQL_PORT or int(secret.get("port", 3306)),
        user=secret["username"],
        password=secret["password"],
        database=MYSQL_DATABASE,
        connect_timeout=5,
        read_timeout=5,
        write_timeout=5,
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def ensure_database():
    if not MYSQL_SECRET_ARN:
        return
    connection = database_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS orders (
                    order_id CHAR(36) PRIMARY KEY,
                    status VARCHAR(24) NOT NULL,
                    items JSON NOT NULL,
                    total DECIMAL(12, 2) NOT NULL,
                    email VARCHAR(254) NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS order_outbox (
                    event_id CHAR(36) PRIMARY KEY,
                    order_id CHAR(36) NOT NULL,
                    event_type VARCHAR(64) NOT NULL,
                    detail JSON NOT NULL,
                    published_at TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX outbox_pending (published_at, created_at)
                )"""
            )
        connection.commit()
    finally:
        connection.close()


def persist_order(order):
    connection = database_connection()
    event_id = str(uuid.uuid4())
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orders (order_id, status, items, total, email) VALUES (%s, %s, %s, %s, %s)",
                (order["orderId"], order["status"], json.dumps(order["items"]), order["total"], order.get("email")),
            )
            if EVENT_BUS_NAME:
                cursor.execute(
                    "INSERT INTO order_outbox (event_id, order_id, event_type, detail) VALUES (%s, %s, %s, %s)",
                    (event_id, order["orderId"], "OrderCreated", json.dumps({"eventId": event_id, "orderId": order["orderId"]})),
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_order(order_id):
    if not MYSQL_SECRET_ARN:
        with ORDERS_LOCK:
            return ORDERS.get(order_id)
    connection = database_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
            record = cursor.fetchone()
        if not record:
            return None
        items = record["items"]
        if isinstance(items, str):
            items = json.loads(items)
        return {
            "orderId": record["order_id"],
            "status": record["status"],
            "items": items,
            "total": float(record["total"]),
            "email": record["email"],
            "event": "OrderCreated",
        }
    finally:
        connection.close()


def publish_pending_events():
    if not (MYSQL_SECRET_ARN and EVENT_BUS_NAME):
        return
    connection = database_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT event_id, order_id, event_type, detail FROM order_outbox "
                "WHERE published_at IS NULL ORDER BY created_at LIMIT 10"
            )
            events = cursor.fetchall()
    finally:
        connection.close()
    if not events:
        return

    client = events_client()
    for event in events:
        response = client.put_events(Entries=[{
            "EventBusName": EVENT_BUS_NAME,
            "Source": "cloudbatch818.retail.orders",
            "DetailType": event["event_type"],
            "Detail": event["detail"] if isinstance(event["detail"], str) else json.dumps(event["detail"]),
        }])
        if response.get("FailedEntryCount", 0):
            raise RuntimeError("EventBridge rejected an order event")
        connection = database_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE order_outbox SET published_at = CURRENT_TIMESTAMP WHERE event_id = %s", (event["event_id"],))
            connection.commit()
        finally:
            connection.close()


def outbox_worker():
    while True:
        try:
            publish_pending_events()
        except Exception as error:
            print(f"Order outbox delivery failed; it will retry: {error}")
        time.sleep(5)


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
        if path in ("/health", "/ready"):
            return self._write(200, {"status": "ok" if path == "/health" else "ready", "service": SERVICE})
        if path.startswith("/orders/"):
            order = get_order(path.split("/")[-1])
            return self._write(200, order) if order else self._write(404, {"error": "order not found"})
        return self._write(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        body = self._read_body()
        if body is None:
            return self._write(400, {"error": "invalid JSON body"})
        if path != "/orders":
            return self._write(404, {"error": "not found"})
        if not isinstance(body, dict) or not isinstance(body.get("items"), list) or not body["items"]:
            return self._write(400, {"error": "items are required"})
        email = body.get("email")
        if email is not None and (not isinstance(email, str) or len(email) > 254 or "@" not in email):
            return self._write(400, {"error": "email must be a valid email address"})

        try:
            if email:
                email = email.strip().lower()
                _, verification = json_request(
                    f"{NOTIFICATION_SERVICE_URL}/email/status", method="POST",
                    body={"email": email, "verificationToken": body.get("verificationToken")},
                )
                if not verification.get("verified"):
                    return self._write(409, {"error": "Verify your email before reserving with email updates."})
            requested = {}
            for item in body["items"]:
                if not isinstance(item, dict):
                    return self._write(400, {"error": "invalid order item"})
                product_id, quantity = item.get("productId"), item.get("quantity", 0)
                if not isinstance(product_id, str) or type(quantity) is not int or quantity < 1:
                    return self._write(400, {"error": "quantity must be a positive integer"})
                requested[product_id] = requested.get(product_id, 0) + quantity

            product_items = []
            total = Decimal("0.00")
            normalized_items = [{"productId": key, "quantity": value} for key, value in requested.items()]
            for item in normalized_items:
                _, product = json_request(f"{PRODUCT_SERVICE_URL}/products/{item['productId']}")
                line_total = Decimal(str(product["price"])) * item["quantity"]
                total += line_total
                product_items.append({
                    **item,
                    "name": product["name"],
                    "unitPrice": product["price"],
                    "lineTotal": float(line_total),
                })
            _, inventory = json_request(
                f"{INVENTORY_SERVICE_URL}/inventory/reservations",
                method="POST",
                body={"items": normalized_items},
            )
        except HTTPError as error:
            details = json.loads(error.read() or b"{}")
            return self._write(error.code, details)
        except (URLError, TimeoutError):
            return self._write(503, {"error": "dependent service unavailable"})

        order = {
            "orderId": str(uuid.uuid4()),
            "status": "CONFIRMED",
            "items": product_items,
            "total": float(total),
            "email": email,
            "inventory": inventory,
            "event": "OrderCreated",
        }
        try:
            if MYSQL_SECRET_ARN:
                persist_order(order)
            else:
                with ORDERS_LOCK:
                    ORDERS[order["orderId"]] = order
        except Exception as error:
            try:
                json_request(
                    f"{INVENTORY_SERVICE_URL}/inventory/releases",
                    method="POST",
                    body={"items": normalized_items},
                )
            except Exception as release_error:
                print(f"Inventory compensation failed for {order['orderId']}: {release_error}")
            print(f"Order persistence failed: {error}")
            return self._write(503, {"error": "order could not be saved; inventory release requested"})
        return self._write(201, order)

    def log_message(self, fmt, *args):
        print(f"[{SERVICE}] {fmt % args}")


def main():
    if MYSQL_SECRET_ARN:
        ensure_database()
    if EVENT_BUS_NAME and MYSQL_SECRET_ARN:
        threading.Thread(target=outbox_worker, daemon=True).start()
    print(f"Starting {SERVICE} on port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
