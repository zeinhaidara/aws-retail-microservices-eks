import importlib.util
import json
import pathlib
import sys
import unittest
from unittest.mock import MagicMock, patch


SERVICE_DIR = pathlib.Path(__file__).resolve().parents[1] / "services" / "order-service"
sys.path.insert(0, str(SERVICE_DIR))
spec = importlib.util.spec_from_file_location("order_outbox_app", SERVICE_DIR / "app.py")
order = importlib.util.module_from_spec(spec)
spec.loader.exec_module(order)
sys.path.pop(0)


class OrderOutboxTests(unittest.TestCase):
    def setUp(self):
        self.pending = [{
            "event_id": "event-1", "order_id": "order-1",
            "event_type": "OrderCreated",
            "detail": json.dumps({"eventId": "event-1", "orderId": "order-1"}),
        }]
        self.client = MagicMock()
        self.client.put_events.return_value = {"FailedEntryCount": 0}
        self.connections = []

    def connection(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.side_effect = lambda: list(self.pending)
        connection.commit.side_effect = self.pending.clear
        self.connections.append(connection)
        return connection

    def publish(self):
        with patch.object(order, "MYSQL_SECRET_ARN", "test-secret"), \
             patch.object(order, "EVENT_BUS_NAME", "test-bus"), \
             patch.object(order, "database_connection", side_effect=self.connection), \
             patch.object(order, "events_client", return_value=self.client):
            order.publish_pending_events()

    def test_accepted_event_is_committed_and_not_republished(self):
        with patch.object(order, "event") as metric:
            self.publish()
            self.publish()
        self.client.put_events.assert_called_once_with(Entries=[{
            "EventBusName": "test-bus",
            "Source": "cloudbatch818.retail.orders",
            "DetailType": "OrderCreated",
            "Detail": json.dumps({"eventId": "event-1", "orderId": "order-1"}),
        }])
        update = self.connections[1]
        update.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
            "UPDATE order_outbox SET published_at = CURRENT_TIMESTAMP WHERE event_id = %s",
            ("event-1",),
        )
        update.commit.assert_called_once()
        metric.assert_called_once_with("outbox_published")
        for connection in self.connections:
            connection.close.assert_called_once()

    def test_rejected_event_remains_pending_for_retry(self):
        self.client.put_events.return_value = {"FailedEntryCount": 1}
        with patch.object(order, "event") as metric:
            with self.assertRaisesRegex(RuntimeError, "EventBridge rejected"):
                self.publish()
            self.assertEqual(len(self.pending), 1)
            self.connections[0].commit.assert_not_called()
            metric.assert_not_called()
            self.client.put_events.return_value = {"FailedEntryCount": 0}
            self.publish()
        self.assertEqual(self.client.put_events.call_count, 2)
        self.assertEqual(self.pending, [])

    def test_metrics_failure_does_not_leave_event_pending(self):
        with patch.object(order, "event", side_effect=RuntimeError("metrics failed")):
            with self.assertRaisesRegex(RuntimeError, "metrics failed"):
                self.publish()
            self.publish()
        self.assertEqual(self.pending, [])
        self.client.put_events.assert_called_once()


if __name__ == "__main__":
    unittest.main()
