variable "name" { type = string }
variable "policy_name" { type = string }
variable "oidc_provider_arn" { type = string }
variable "oidc_issuer_url" { type = string }
variable "namespace" { type = string }
variable "service_account" { type = string }
variable "permissions_policy" { type = any }
variable "tags" { type = map(string) }

locals {
  oidc_issuer = trimprefix(var.oidc_issuer_url, "https://")
}

resource "aws_iam_role" "this" {
  name = var.name
  tags = var.tags
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = var.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = { StringEquals = {
        "${local.oidc_issuer}:aud" = "sts.amazonaws.com"
        "${local.oidc_issuer}:sub" = "system:serviceaccount:${var.namespace}:${var.service_account}"
      } }
    }]
  })
}

resource "aws_iam_role_policy" "this" {
  name   = var.policy_name
  role   = aws_iam_role.this.id
  policy = jsonencode(var.permissions_policy)
}

output "arn" { value = aws_iam_role.this.arn }
