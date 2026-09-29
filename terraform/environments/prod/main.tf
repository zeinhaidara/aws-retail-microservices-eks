module "platform" {
  source             = "../../modules/platform"
  name               = local.name
  vpc_cidr           = var.vpc_cidr
  enable_nat_gateway = var.enable_nat_gateway
  cluster_version    = var.cluster_version
  services           = toset(["product", "inventory", "order", "notification"])
}
