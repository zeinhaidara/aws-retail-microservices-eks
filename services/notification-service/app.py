import json
import os
import secrets
import threading
import time
from functools import lru_cache
from http.server import ThreadingHTTPServer
from metrics import MetricsHandler, event
from urllib.request import urlopen


SERVICE = "notification-service"
PORT = int(os.getenv("PORT", "8080"))
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
ORDER_EVENTS_QUEUE_URL = os.getenv("ORDER_EVENTS_QUEUE_URL", "")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8080")
SES_FROM_ADDRESS = os.getenv("SES_FROM_ADDRESS", "")
VERIFICATIONS = {}
VERIFICATION_LOCK = threading.Lock()
SEND_TIMES = []


@lru_cache(maxsize=1)
def verification_client():
    import boto3

    return boto3.client("ses", region_name=AWS_REGION)


def normalize_email(email):
    if not isinstance(email, str) or len(email) > 254:
        raise ValueError("Enter a valid email address.")
    email = email.strip().lower()
    if email.count("@") != 1 or any(character.isspace() for character in email):
        raise ValueError("Enter a valid email address.")
    local, domain = email.split("@")
    labels = domain.split(".")
    if not local or len(labels) < 2 or any(not label for label in labels):
        raise ValueError("Enter a valid email address.")
    return email


def is_verified(email):
    client = ses_client()
    try:
        return bool(client.get_email_identity(EmailIdentity=email).get("VerifiedForSendingStatus"))
    except client.exceptions.NotFoundException:
        return False


def request_verification(email):
    email = normalize_email(email)
    if not SES_FROM_ADDRESS:
        raise RuntimeError("Email notifications are not configured.")
    now = time.monotonic()
    with VERIFICATION_LOCK:
        for address in list(VERIFICATIONS):
            if now - VERIFICATIONS[address]["created"] > 86400:
                del VERIFICATIONS[address]
        previous = VERIFICATIONS.get(email)
        if previous and now - previous["created"] < 60:
            raise ValueError("Wait 60 seconds before requesting another verification email.")
        SEND_TIMES[:] = [stamp for stamp in SEND_TIMES if now - stamp < 3600]
        if len(SEND_TIMES) >= 100 or sum(now - stamp < 60 for stamp in SEND_TIMES) >= 10:
            raise ValueError("Verification limit reached. Try again later.")
        token = secrets.token_urlsafe(32)
        VERIFICATIONS[email] = {"token": token, "created": now}
        SEND_TIMES.append(now)
    verified = is_verified(email)
    if not verified:
        verification_client().verify_email_identity(EmailAddress=email)
    return {"email": email, "verificationToken": token, "verified": verified}


def verification_status(email, token):
    email = normalize_email(email)
    with VERIFICATION_LOCK:
        entry = VERIFICATIONS.get(email)
        valid = (isinstance(token, str) and entry and
                 time.monotonic() - entry["created"] <= 86400 and
                 secrets.compare_digest(entry["token"], token))
    if not valid:
        raise ValueError("Request email verification again; this session has expired.")
    with VERIFICATION_LOCK:
        if time.monotonic() - entry.get("checked", 0) >= 5:
            entry["verified"] = is_verified(email)
            entry["checked"] = time.monotonic()
        return {"verified": entry.get("verified", False)}


@lru_cache(maxsize=1)
def ses_client():
    import boto3

    return boto3.client("sesv2", region_name=AWS_REGION)


def order_details(order_id):
    with urlopen(f"{ORDER_SERVICE_URL}/orders/{order_id}", timeout=5) as response:
        return json.loads(response.read() or b"{}")


def send_confirmation(order):
    recipient = order.get("email")
    if not recipient:
        return
    if not SES_FROM_ADDRESS:
        raise RuntimeError("Email sender is not configured")

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
    event("email_sent")


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
                    event("email_failed")
                    print(f"Order event failed; SQS will retry it: {error}")
        except Exception as error:
            print(f"Order event polling failed; retrying: {error}")
            time.sleep(5)


class Handler(MetricsHandler):
    def _write(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path not in ("/email/verify", "/email/status"):
            return self._write(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                return self._write(400, {"error": "invalid request size"})
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                return self._write(400, {"error": "invalid JSON body"})
            if self.path == "/email/verify":
                result = request_verification(body.get("email"))
            else:
                result = verification_status(body.get("email"), body.get("verificationToken"))
            return self._write(200, result)
        except (ValueError, json.JSONDecodeError) as error:
            return self._write(400, {"error": str(error)})
        except Exception as error:
            print(f"Email verification failed: {type(error).__name__}")
            return self._write(503, {"error": "Email verification unavailable. Try again later."})

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



def main():
    if ORDER_EVENTS_QUEUE_URL:
        threading.Thread(target=consume_events, daemon=True).start()
    print(f"Starting {SERVICE} on port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
