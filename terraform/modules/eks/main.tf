variable "name" { type = string }
variable "cluster_version" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "tags" { type = map(string) }

# Temporary dev-demo exceptions: GitHub-hosted deployments require the public API,
# and workloads call external registries and AI APIs. Revisit before wider use.
#trivy:ignore:AVD-AWS-0040:exp:2026-11-01
#trivy:ignore:AVD-AWS-0041:exp:2026-11-01
#trivy:ignore:AVD-AWS-0104:exp:2026-11-01
module "eks" {
  source                                   = "terraform-aws-modules/eks/aws"
  version                                  = "~> 21.0"
  name                                     = var.name
  kubernetes_version                       = var.cluster_version
  endpoint_public_access                   = true
  enable_irsa                              = true
  vpc_id                                   = var.vpc_id
  subnet_ids                               = var.subnet_ids
  enable_cluster_creator_admin_permissions = true
  tags                                     = var.tags
  cluster_tags                             = var.tags
  node_security_group_tags                 = var.tags
  eks_managed_node_groups = {
    default = {
      instance_types       = ["t3.medium"]
      capacity_type        = "ON_DEMAND"
      min_size             = 1
      max_size             = 3
      desired_size         = 1
      tags                 = var.tags
      launch_template_tags = var.tags
      tag_specifications   = ["instance", "volume", "network-interface"]
    }
  }
}

output "cluster_name" { value = module.eks.cluster_name }
output "cluster_endpoint" { value = module.eks.cluster_endpoint }
output "node_security_group_id" { value = module.eks.node_security_group_id }
output "oidc_provider_arn" { value = module.eks.oidc_provider_arn }
output "cluster_oidc_issuer_url" { value = module.eks.cluster_oidc_issuer_url }
