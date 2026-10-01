variable "aws_region" { type = string }
variable "environment" {
  type    = string
  default = "test"
}
variable "project_name" {
  type    = string
  default = "cloudbatch818"
  validation {
    condition     = var.project_name == "cloudbatch818"
    error_message = "Project resource names must use the cloudbatch818 prefix."
  }
}

variable "owner" {
  type    = string
  default = "zein"
  validation {
    condition     = var.owner == "zein"
    error_message = "Resource names must use the zein owner prefix."
  }
}
variable "vpc_cidr" {
  type    = string
  default = "10.50.0.0/16"
}
variable "cluster_version" {
  type    = string
  default = "1.36"
}
variable "enable_nat_gateway" {
  type    = bool
  default = true
}

variable "domain_name" {
  type        = string
  description = "Public storefront hostname covered by the ACM certificate."
}

variable "route53_zone_id" {
  type        = string
  description = "ID of the existing public Route 53 hosted zone for domain_name."
}
