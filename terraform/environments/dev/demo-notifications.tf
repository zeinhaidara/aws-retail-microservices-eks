variable "demo_notification_email" {
  description = "Optional demo recipient to verify for SES sandbox delivery."
  type        = string
  default     = ""

  validation {
    condition     = var.demo_notification_email == "" || can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.demo_notification_email))
    error_message = "Provide a valid email address or leave it empty."
  }
}

resource "aws_sesv2_email_identity" "demo_recipient" {
  count          = var.demo_notification_email == "" ? 0 : 1
  email_identity = var.demo_notification_email
  tags           = local.common_tags
}
