terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

variable "aws_region" { type = string }
variable "owner" {
  type    = string
  default = "zein"
  validation {
    condition     = var.owner == "zein"
    error_message = "Resource names must use the zein owner prefix."
  }
}
variable "project_name" {
  type    = string
  default = "cloudbatch818"
  validation {
    condition     = var.project_name == "cloudbatch818"
    error_message = "Project resource names must use the cloudbatch818 prefix."
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Owner     = var.owner
      Project   = "Cloudbatch818"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  name_prefix       = "${var.project_name}-${var.owner}"
  state_bucket_name = "${local.name_prefix}-terraform-state-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket" "terraform_state" {
  bucket = local.state_bucket_name
  tags = {
    Owner     = var.owner
    Project   = "Cloudbatch818"
    ManagedBy = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket                  = aws_s3_bucket.terraform_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "state_bucket_name" {
  value = aws_s3_bucket.terraform_state.bucket
}
