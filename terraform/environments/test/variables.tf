variable "aws_region" { type = string }
variable "environment" {
  type    = string
  default = "test"
}
variable "project_name" {
  type    = string
  default = "retail"
}
variable "vpc_cidr" {
  type    = string
  default = "10.50.0.0/16"
}
variable "cluster_version" {
  type    = string
  default = "1.33"
}
variable "enable_nat_gateway" {
  type    = bool
  default = true
}
