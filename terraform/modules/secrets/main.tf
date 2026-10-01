variable "name" { type = string }
variable "oidc_provider_arn" { type = string }
variable "oidc_issuer_url" { type = string }
variable "tags" { type = map(string) }

variable "managed_secrets" {
  type = map(object({
    service     = string
    purpose     = string
    description = string
  }))
}

resource "aws_secretsmanager_secret" "runtime" {
  for_each = var.managed_secrets

  name                    = "${var.name}/services/${each.value.service}/${each.value.purpose}"
  description             = each.value.description
  recovery_window_in_days = 7
  tags                    = var.tags
}

module "external_secrets_role" {
  source            = "../irsa-role"
  name              = "${var.name}-external-secrets"
  policy_name       = "read-runtime-secrets"
  oidc_provider_arn = var.oidc_provider_arn
  oidc_issuer_url   = var.oidc_issuer_url
  namespace         = "external-secrets"
  service_account   = "external-secrets"
  permissions_policy = {
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue"]
      Resource = [for secret in values(aws_secretsmanager_secret.runtime) : secret.arn]
    }]
  }
  tags = var.tags
}

moved {
  from = aws_iam_role.external_secrets
  to   = module.external_secrets_role.aws_iam_role.this
}

moved {
  from = aws_iam_role_policy.external_secrets
  to   = module.external_secrets_role.aws_iam_role_policy.this
}

output "secret_names" {
  value = { for key, secret in aws_secretsmanager_secret.runtime : key => secret.name }
}

output "external_secrets_role_arn" {
  value = module.external_secrets_role.arn
}
