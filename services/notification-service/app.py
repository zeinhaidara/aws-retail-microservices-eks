import json
import os
import threading
import time
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen


SERVICE = "notification-service"
PORT = int(os.getenv("PORT", "8080"))
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
ORDER_EVENTS_QUEUE_URL = os.getenv("ORDER_EVENTS_QUEUE_URL", "")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8080")
SES_FROM_ADDRESS = os.getenv("SES_FROM_ADDRESS", "")


@lru_cache(maxsize=1)
def ses_client():
    import boto3

    return boto3.client("sesv2", region_name=AWS_REGION)


def order_details(order_id):
    with urlopen(f"{ORDER_SERVICE_URL}/orders/{order_id}", timeout=5) as response:
        return json.loads(response.read() or b"{}")


def send_confirmation(order):
    recipient = order.get("email")
    if not recipient or not SES_FROM_ADDRESS:
        print(f"Order confirmation ready for {order['orderId']}; email sender or recipient is not configured")
        return

    destinations = ", ".join(f"{item['quantity']} x {item['name']}" for item in order["items"])
    subject = f"Your Orbital Expeditions reservation {order['orderId']}"
    body = (
        "Thank you for your Orbital Expeditions reservation.\n\n"
        f"Reference: {order['orderId']}\n"
        f"Itinerary: {destinations}\n"
        f"Total: ${order['total']:,.2f}\n\n"
        "This is a fictional travel concept, not an operational booking."
    )
    ses_client().send_email(
        FromEmailAddress=SES_FROM_ADDRESS,
        Destination={"ToAddresses": [recipient]},
        Content={"Simple": {
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
        }},
    )
    print(f"Sent order confirmation for {order['orderId']} to {recipient}")


def process_message(message):
    envelope = json.loads(message["Body"])
    detail = envelope.get("detail", envelope)
    order = order_details(detail["orderId"])
    send_confirmation(order)


def consume_events():
    import boto3

    client = boto3.client("sqs", region_name=AWS_REGION)
    while True:
        try:
            response = client.receive_message(
                QueueUrl=ORDER_EVENTS_QUEUE_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
                VisibilityTimeout=60,
            )
            for message in response.get("Messages", []):
                try:
                    process_message(message)
                    client.delete_message(QueueUrl=ORDER_EVENTS_QUEUE_URL, ReceiptHandle=message["ReceiptHandle"])
                except Exception as error:
                    print(f"Order event failed; SQS will retry it: {error}")
        except Exception as error:
            print(f"Order event polling failed; retrying: {error}")
            time.sleep(5)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") in ("/health", "/ready"):
            status = "ok" if self.path.rstrip("/") == "/health" else "ready"
            body = json.dumps({"status": status, "service": SERVICE}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, fmt, *args):
        print(f"[{SERVICE}] {fmt % args}")


def main():
    if ORDER_EVENTS_QUEUE_URL:
        threading.Thread(target=consume_events, daemon=True).start()
    print(f"Starting {SERVICE} on port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
