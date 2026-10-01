module "platform" {
  source             = "../../modules/platform"
  name               = local.name
  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  enable_nat_gateway = var.enable_nat_gateway
  cluster_version    = var.cluster_version
  domain_name        = var.domain_name
  route53_zone_id    = var.route53_zone_id
  tags               = local.common_tags
}
