locals {
  name = "${var.project_name}-${var.owner}-${var.environment}"
  common_tags = {
    Owner       = var.owner
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
