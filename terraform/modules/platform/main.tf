variable "name" { type = string }
variable "vpc_cidr" { type = string }
variable "enable_nat_gateway" { type = bool }
variable "cluster_version" { type = string }
variable "services" { type = set(string) }

module "network" {
  source             = "../network"
  name               = var.name
  vpc_cidr           = var.vpc_cidr
  enable_nat_gateway = var.enable_nat_gateway
}

module "eks" {
  source          = "../eks"
  name            = var.name
  cluster_version = var.cluster_version
  vpc_id          = module.network.vpc_id
  subnet_ids      = module.network.private_subnets
}

module "ecr" {
  source   = "../ecr"
  name     = var.name
  services = var.services
}

module "data" {
  source = "../data"
  name   = var.name
}

module "messaging" {
  source = "../messaging"
  name   = var.name
}

output "cluster_name" { value = module.eks.cluster_name }
output "cluster_endpoint" { value = module.eks.cluster_endpoint }
output "ecr_repository_urls" { value = module.ecr.repository_urls }
output "inventory_table_name" { value = module.data.inventory_table_name }
output "order_events_queue_url" { value = module.messaging.order_events_queue_url }
output "order_events_queue_arn" { value = module.messaging.order_events_queue_arn }
output "event_bus_name" { value = module.messaging.event_bus_name }
