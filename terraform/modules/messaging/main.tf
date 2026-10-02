variable "name" { type = string }
variable "tags" { type = map(string) }

resource "aws_sqs_queue" "order_events_dlq" {
  name                    = "${var.name}-order-events-dlq"
  sqs_managed_sse_enabled = true
  tags                    = var.tags
}

resource "aws_sqs_queue" "order_events" {
  name                       = "${var.name}-order-events"
  visibility_timeout_seconds = 60
  sqs_managed_sse_enabled    = true
  tags                       = var.tags
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.order_events_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_cloudwatch_event_bus" "retail" {
  name = "${var.name}-events"
  tags = var.tags
}

data "aws_caller_identity" "current" {}

resource "aws_cloudwatch_event_rule" "order_created" {
  name           = "${var.name}-order-created"
  event_bus_name = aws_cloudwatch_event_bus.retail.name
  event_pattern = jsonencode({
    source        = ["cloudbatch818.retail.orders"]
    "detail-type" = ["OrderCreated"]
  })
  tags = var.tags
}

resource "aws_cloudwatch_event_target" "order_events" {
  rule           = aws_cloudwatch_event_rule.order_created.name
  event_bus_name = aws_cloudwatch_event_bus.retail.name
  target_id      = "order-events-queue"
  arn            = aws_sqs_queue.order_events.arn
}

resource "aws_sqs_queue_policy" "allow_eventbridge" {
  queue_url = aws_sqs_queue.order_events.url
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowMatchingOrderEvents"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.order_events.arn
      Condition = {
        ArnEquals    = { "aws:SourceArn" = aws_cloudwatch_event_rule.order_created.arn }
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
      }
    }]
  })
}

output "order_events_queue_url" { value = aws_sqs_queue.order_events.url }
output "order_events_queue_arn" { value = aws_sqs_queue.order_events.arn }
output "event_bus_name" { value = aws_cloudwatch_event_bus.retail.name }
output "event_bus_arn" { value = aws_cloudwatch_event_bus.retail.arn }
