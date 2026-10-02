variable "name" { type = string }
variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Environment must be dev, test, or prod."
  }
}
variable "vpc_cidr" { type = string }
variable "enable_nat_gateway" { type = bool }
variable "cluster_version" { type = string }
variable "domain_name" { type = string }
variable "route53_zone_id" { type = string }
variable "tags" { type = map(string) }

locals {
  services = toset(["product", "inventory", "order", "notification", "trip-planner", "storefront"])
}

module "network" {
  source             = "../network"
  name               = var.name
  vpc_cidr           = var.vpc_cidr
  enable_nat_gateway = var.enable_nat_gateway
  tags               = var.tags
}

module "eks" {
  source          = "../eks"
  name            = var.name
  environment     = var.environment
  cluster_version = var.cluster_version
  vpc_id          = module.network.vpc_id
  subnet_ids      = module.network.private_subnets
  tags            = var.tags
}

module "ecr" {
  source   = "../ecr"
  name     = var.name
  services = local.services
  tags     = var.tags
}

module "data" {
  source                        = "../data"
  name                          = var.name
  tags                          = var.tags
  vpc_id                        = module.network.vpc_id
  private_subnet_ids            = module.network.private_subnets
  eks_cluster_security_group_id = module.eks.cluster_primary_security_group_id
}

module "messaging" {
  source = "../messaging"
  name   = var.name
  tags   = var.tags
}

module "inventory_role" {
  source            = "../irsa-role"
  name              = "${var.name}-inventory"
  policy_name       = "inventory-table-access"
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_issuer_url   = module.eks.cluster_oidc_issuer_url
  namespace         = "retail-${var.environment}"
  service_account   = "retail-inventory"
  tags              = var.tags
  permissions_policy = {
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:ConditionCheckItem",
        "dynamodb:DeleteItem",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:ReadDataForReplication",
        "dynamodb:UpdateItem",
      ]
      Resource = [module.data.inventory_table_arn]
    }]
  }
}

module "order_role" {
  source            = "../irsa-role"
  name              = "${var.name}-order"
  policy_name       = "order-database-events"
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_issuer_url   = module.eks.cluster_oidc_issuer_url
  namespace         = "retail-${var.environment}"
  service_account   = "retail-order"
  tags              = var.tags
  permissions_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [module.data.mysql_master_secret_arn]
      },
      {
        Effect   = "Allow"
        Action   = ["events:PutEvents"]
        Resource = [module.messaging.event_bus_arn]
      }
    ]
  }
}

module "notification_role" {
  source            = "../irsa-role"
  name              = "${var.name}-notification"
  policy_name       = "notification-queue-email"
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_issuer_url   = module.eks.cluster_oidc_issuer_url
  namespace         = "retail-${var.environment}"
  service_account   = "retail-notification"
  tags              = var.tags
  permissions_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = [module.messaging.order_events_queue_arn]
      },
      {
        Effect   = "Allow"
        Action   = ["ses:SendEmail"]
        Resource = [module.edge.ses_identity_arn]
      }
    ]
  }
}

module "secrets" {
  source            = "../secrets"
  name              = var.name
  tags              = var.tags
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_issuer_url   = module.eks.cluster_oidc_issuer_url
  managed_secrets = {
    cloudflare = {
      service     = "trip-planner"
      purpose     = "cloudflare"
      description = "Cloudflare Workers AI credentials"
    }
    gemini = {
      service     = "trip-planner"
      purpose     = "gemini"
      description = "Gemini API credentials"
    }
  }
}

module "edge" {
  source              = "../edge"
  name                = var.name
  domain_name         = var.domain_name
  route53_zone_id     = var.route53_zone_id
  create_ses_identity = var.environment == "dev"
  tags                = var.tags
  oidc_provider_arn   = module.eks.oidc_provider_arn
  oidc_issuer_url     = module.eks.cluster_oidc_issuer_url
}

output "cluster_name" { value = module.eks.cluster_name }
output "cluster_endpoint" { value = module.eks.cluster_endpoint }
output "ecr_repository_urls" { value = module.ecr.repository_urls }
output "inventory_table_name" { value = module.data.inventory_table_name }
output "inventory_table_arn" { value = module.data.inventory_table_arn }
output "mysql_endpoint" { value = module.data.mysql_endpoint }
output "mysql_port" { value = module.data.mysql_port }
output "mysql_database_name" { value = module.data.mysql_database_name }
output "mysql_master_secret_arn" { value = module.data.mysql_master_secret_arn }
output "valkey_endpoint" { value = module.data.valkey_endpoint }
output "valkey_port" { value = module.data.valkey_port }
output "order_events_queue_url" { value = module.messaging.order_events_queue_url }
output "order_events_queue_arn" { value = module.messaging.order_events_queue_arn }
output "event_bus_name" { value = module.messaging.event_bus_name }
output "event_bus_arn" { value = module.messaging.event_bus_arn }
output "inventory_role_arn" { value = module.inventory_role.arn }
output "order_role_arn" { value = module.order_role.arn }
output "notification_role_arn" { value = module.notification_role.arn }
output "runtime_secret_names" { value = module.secrets.secret_names }
output "cloudflare_secret_name" { value = module.secrets.secret_names["cloudflare"] }
output "gemini_secret_name" { value = module.secrets.secret_names["gemini"] }
output "external_secrets_role_arn" { value = module.secrets.external_secrets_role_arn }
output "vpc_id" { value = module.network.vpc_id }
output "storefront_domain_name" { value = var.domain_name }
output "storefront_certificate_arn" { value = module.edge.certificate_arn }
output "ses_identity_arn" { value = module.edge.ses_identity_arn }
output "ses_from_address" { value = module.edge.ses_from_address }
output "load_balancer_controller_role_arn" { value = module.edge.load_balancer_controller_role_arn }
output "external_dns_role_arn" { value = module.edge.external_dns_role_arn }
