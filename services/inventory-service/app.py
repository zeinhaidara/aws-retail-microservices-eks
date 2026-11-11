import json
import os
import threading
from functools import lru_cache
from http.server import ThreadingHTTPServer
from metrics import MetricsHandler
from urllib.parse import urlparse


SERVICE = "inventory-service"
PORT = int(os.getenv("PORT", "8080"))

INVENTORY = {"orbit-001": 8, "orbit-002": 4, "orbit-003": 6, "orbit-004": 5, "orbit-005": 5, "orbit-006": 12, "orbit-007": 3, "orbit-008": 2, "orbit-009": 2, "orbit-010": 1}
PRODUCT_IDS = tuple(INVENTORY)
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "")
INVENTORY_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def inventory_table():
    if not DYNAMODB_TABLE_NAME:
        return None
    import boto3

    return boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION")).Table(DYNAMODB_TABLE_NAME)


def seed_inventory():
    table = inventory_table()
    if not table:
        return
    from boto3.dynamodb.conditions import Attr

    for product_id, available in INVENTORY.items():
        try:
            table.put_item(
                Item={"sku": product_id, "available": available},
                ConditionExpression=Attr("sku").not_exists(),
            )
        except table.meta.client.exceptions.ConditionalCheckFailedException:
            pass


def get_available(product_id):
    table = inventory_table()
    if table:
        response = table.meta.client.get_item(
            TableName=DYNAMODB_TABLE_NAME,
            Key={"sku": product_id},
            ConsistentRead=True,
        )
        item = response.get("Item")
        # DynamoDB numbers deserialize as Decimal, which json.dumps cannot encode.
        return int(item["available"]) if item else None
    with INVENTORY_LOCK:
        return INVENTORY.get(product_id)


def inventory_items():
    return [
        {"productId": product_id, "available": get_available(product_id)}
        for product_id in PRODUCT_IDS
    ]


def update_inventory(items, release=False):
    table = inventory_table()
    if table:
        operations = []
        for item in items:
            quantity = item["quantity"]
            if release:
                operations.append({"Update": {
                    "TableName": DYNAMODB_TABLE_NAME,
                    "Key": {"sku": item["productId"]},
                    "UpdateExpression": "SET available = available + :quantity",
                    "ConditionExpression": "attribute_exists(sku)",
                    "ExpressionAttributeValues": {":quantity": quantity},
                }})
            else:
                operations.append({"Update": {
                    "TableName": DYNAMODB_TABLE_NAME,
                    "Key": {"sku": item["productId"]},
                    "UpdateExpression": "SET available = available - :quantity",
                    "ConditionExpression": "available >= :quantity",
                    "ExpressionAttributeValues": {":quantity": quantity},
                }})
        try:
            table.meta.client.transact_write_items(TransactItems=operations)
        except table.meta.client.exceptions.TransactionCanceledException:
            return False
        return True

    with INVENTORY_LOCK:
        if not release and any(INVENTORY.get(item["productId"], -1) < item["quantity"] for item in items):
            return False
        for item in items:
            product_id, quantity = item["productId"], item["quantity"]
            INVENTORY[product_id] = INVENTORY.get(product_id, 0) + (quantity if release else -quantity)
    return True



class Handler(MetricsHandler):
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

        if path.startswith("/inventory/"):
            product_id = path.split("/")[-1]
            available = get_available(product_id)
            if available is None:
                return self._write(404, {"error": "inventory not found"})
            return self._write(200, {"productId": product_id, "available": available})
        if path == "/inventory":
            return self._write(200, {"items": inventory_items()})


        return self._write(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        body = self._read_body()
        if body is None:
            return self._write(400, {"error": "invalid JSON body"})

        if path == "/inventory/reservations":
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
            reserved = [{"productId": product_id, "quantity": quantity} for product_id, quantity in requested.items()]
            if not update_inventory(reserved):
                return self._write(409, {"error": "insufficient inventory"})
            return self._write(201, {"status": "RESERVED", "items": reserved, "event": "InventoryReserved"})

        if path == "/inventory/releases":
            if not isinstance(body, dict) or not isinstance(body.get("items"), list) or not body["items"]:
                return self._write(400, {"error": "items are required"})
            items = body["items"]
            if any(
                not isinstance(item, dict)
                or item.get("productId") not in INVENTORY
                or type(item.get("quantity")) is not int
                or item["quantity"] < 1
                for item in items
            ):
                return self._write(400, {"error": "invalid inventory item"})
            if not update_inventory(items, release=True):
                return self._write(409, {"error": "inventory release failed"})
            return self._write(200, {"status": "RELEASED", "items": items})


        return self._write(404, {"error": "not found"})



if __name__ == "__main__":
    seed_inventory()
    print(f"Starting {SERVICE} on port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
