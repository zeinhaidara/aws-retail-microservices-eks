variable "name" { type = string }
variable "environment" { type = string }
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
  create_node_security_group               = false
  tags                                     = var.tags
  cluster_tags                             = var.tags
  # Install DNS after the Fargate profiles exist; no EC2 nodes are available.
  addons = {
    coredns = {
      before_compute = false
      configuration_values = jsonencode({
        computeType = "Fargate"
      })
    }
  }
  fargate_profiles = {
    kube_system = {
      name                       = "${var.name}-kube-system"
      iam_role_name              = "${var.name}-fargate-kube-system"
      iam_role_use_name_prefix   = false
      iam_role_attach_cni_policy = false
      subnet_ids                 = var.subnet_ids
      selectors = [
        {
          namespace = "kube-system"
          labels    = { "k8s-app" = "kube-dns" }
        },
        {
          namespace = "kube-system"
          labels    = { "app.kubernetes.io/name" = "aws-load-balancer-controller" }
        },
        {
          namespace = "kube-system"
          labels    = { "app.kubernetes.io/name" = "external-dns" }
        }
      ]
      tags = var.tags
    }
    application = {
      name                       = "${var.name}-application"
      iam_role_name              = "${var.name}-fargate-application"
      iam_role_use_name_prefix   = false
      iam_role_attach_cni_policy = false
      subnet_ids                 = var.subnet_ids
      selectors = [{
        namespace = "retail-${var.environment}"
      }]
      tags = var.tags
    }
  }
}

output "cluster_name" { value = module.eks.cluster_name }
output "cluster_endpoint" { value = module.eks.cluster_endpoint }
output "cluster_primary_security_group_id" { value = module.eks.cluster_primary_security_group_id }
output "oidc_provider_arn" { value = module.eks.oidc_provider_arn }
output "cluster_oidc_issuer_url" { value = module.eks.cluster_oidc_issuer_url }
