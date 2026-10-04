import importlib.util
import pathlib
import unittest
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import Mock, patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("notification", ROOT / "services/notification-service/app.py")
notification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notification)


class VerificationTests(unittest.TestCase):
    def setUp(self):
        notification.VERIFICATIONS.clear()
        notification.SEND_TIMES.clear()
        self.sender = patch.object(notification, "SES_FROM_ADDRESS", "orders@example.com")
        self.sender.start()
        self.addCleanup(self.sender.stop)

    def test_new_recipient_and_confirmation(self):
        client = Mock()
        with patch.object(notification, "is_verified", side_effect=[False, True]), patch.object(notification, "verification_client", return_value=client):
            result = notification.request_verification(" Visitor@Example.com ")
            self.assertFalse(result["verified"])
            client.verify_email_identity.assert_called_once_with(EmailAddress="visitor@example.com")
            self.assertTrue(notification.verification_status(result["email"], result["verificationToken"])["verified"])

    def test_verified_recipient_does_not_resend(self):
        with patch.object(notification, "is_verified", return_value=True), patch.object(notification, "verification_client") as client:
            self.assertTrue(notification.request_verification("visitor@example.com")["verified"])
            client.assert_not_called()

    def test_invalid_addresses(self):
        for value in (None, "bad", "a@b", "a\n@example.com", {}, "x" * 255):
            with self.assertRaises(ValueError):
                notification.request_verification(value)

    def test_cooldown_and_wrong_token(self):
        with patch.object(notification, "is_verified", return_value=True):
            notification.request_verification("visitor@example.com")
            with self.assertRaises(ValueError):
                notification.request_verification("visitor@example.com")
            with self.assertRaises(ValueError):
                notification.verification_status("visitor@example.com", "wrong")

    def test_global_limit(self):
        with patch.object(notification, "is_verified", return_value=True):
            for number in range(10):
                notification.request_verification(f"visitor{number}@example.com")
            with self.assertRaises(ValueError):
                notification.request_verification("next@example.com")

    def test_sender_missing_does_not_acknowledge_email(self):
        with patch.object(notification, "SES_FROM_ADDRESS", ""):
            with self.assertRaises(RuntimeError):
                notification.send_confirmation({"orderId": "123", "email": "visitor@example.com"})

    def test_pending_and_expired_session(self):
        with patch.object(notification, "is_verified", return_value=False), patch.object(notification, "verification_client"):
            result = notification.request_verification("visitor@example.com")
            self.assertFalse(notification.verification_status(result["email"], result["verificationToken"])["verified"])
            notification.VERIFICATIONS[result["email"]]["created"] -= 86401
            with self.assertRaises(ValueError):
                notification.verification_status(result["email"], result["verificationToken"])


class OrderGateTests(unittest.TestCase):
    def test_pending_email_rejected_before_inventory(self):
        spec = importlib.util.spec_from_file_location("order", ROOT / "services/order-service/app.py")
        order = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(order)
        server = ThreadingHTTPServer(("127.0.0.1", 0), order.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(order, "json_request", return_value=(200, {"verified": False})) as backend:
                data = json.dumps({"email": "visitor@example.com", "verificationToken": "token", "items": [{"productId": "orbit-001", "quantity": 1}]}).encode()
                request = Request(f"http://127.0.0.1:{server.server_port}/orders", data=data, headers={"Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as response:
                    urlopen(request, timeout=5)
                self.assertEqual(response.exception.code, 409)
                self.assertEqual(backend.call_count, 1)
                self.assertTrue(backend.call_args.args[0].endswith("/email/status"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
