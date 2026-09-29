variable "aws_region" {
  type = string
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "project_name" {
  type    = string
  default = "retail"
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "cluster_version" {
  type    = string
  default = "1.33"
}

variable "enable_nat_gateway" {
  type    = bool
  default = true
}

