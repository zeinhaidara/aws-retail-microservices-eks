variable "name" { type = string }

resource "aws_sqs_queue" "order_events_dlq" {
  name = "${var.name}-order-events-dlq"
}

resource "aws_sqs_queue" "order_events" {
  name                       = "${var.name}-order-events"
  visibility_timeout_seconds = 60
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.order_events_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_cloudwatch_event_bus" "retail" {
  name = "${var.name}-events"
}

output "order_events_queue_url" { value = aws_sqs_queue.order_events.url }
output "order_events_queue_arn" { value = aws_sqs_queue.order_events.arn }
output "event_bus_name" { value = aws_cloudwatch_event_bus.retail.name }
