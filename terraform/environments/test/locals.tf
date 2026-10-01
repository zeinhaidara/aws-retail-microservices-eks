locals {
  name = "${var.project_name}-${var.owner}-${var.environment}"
  common_tags = {
    Owner       = var.owner
    Project     = "Cloudbatch818"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
