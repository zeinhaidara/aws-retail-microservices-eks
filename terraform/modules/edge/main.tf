variable "name" { type = string }
variable "domain_name" { type = string }
variable "route53_zone_id" { type = string }
variable "create_ses_identity" { type = bool }
variable "oidc_provider_arn" { type = string }
variable "oidc_issuer_url" { type = string }
variable "tags" { type = map(string) }

locals {
  zone_arn = "arn:${data.aws_partition.current.partition}:route53:::hostedzone/${var.route53_zone_id}"

  # Keep this policy aligned with the pinned AWS Load Balancer Controller chart.
  load_balancer_controller_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = ["iam:CreateServiceLinkedRole"]
        Resource  = "*"
        Condition = { StringEquals = { "iam:AWSServiceName" = "elasticloadbalancing.amazonaws.com" } }
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeAccountAttributes", "ec2:DescribeAddresses", "ec2:DescribeAvailabilityZones",
          "ec2:DescribeInternetGateways", "ec2:DescribeVpcs", "ec2:DescribeVpcPeeringConnections",
          "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups", "ec2:DescribeInstances",
          "ec2:DescribeNetworkInterfaces", "ec2:DescribeTags", "ec2:GetCoipPoolUsage",
          "ec2:DescribeCoipPools", "ec2:GetSecurityGroupsForVpc", "ec2:DescribeIpamPools",
          "ec2:DescribeRouteTables", "elasticloadbalancing:DescribeLoadBalancers",
          "elasticloadbalancing:DescribeLoadBalancerAttributes", "elasticloadbalancing:DescribeListeners",
          "elasticloadbalancing:DescribeListenerCertificates", "elasticloadbalancing:DescribeSSLPolicies",
          "elasticloadbalancing:DescribeRules", "elasticloadbalancing:DescribeTargetGroups",
          "elasticloadbalancing:DescribeTargetGroupAttributes", "elasticloadbalancing:DescribeTargetHealth",
          "elasticloadbalancing:DescribeTags", "elasticloadbalancing:DescribeTrustStores",
          "elasticloadbalancing:DescribeListenerAttributes", "elasticloadbalancing:DescribeCapacityReservation",
          "acm:ListCertificates", "acm:DescribeCertificate"
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:AuthorizeSecurityGroupIngress", "ec2:RevokeSecurityGroupIngress", "ec2:CreateSecurityGroup"]
        Resource = "*"
      },
      {
        Effect    = "Allow"
        Action    = ["ec2:CreateTags"]
        Resource  = "arn:${data.aws_partition.current.partition}:ec2:*:*:security-group/*"
        Condition = { StringEquals = { "ec2:CreateAction" = "CreateSecurityGroup" }, Null = { "aws:RequestTag/elbv2.k8s.aws/cluster" = "false" } }
      },
      {
        Effect    = "Allow"
        Action    = ["ec2:CreateTags", "ec2:DeleteTags"]
        Resource  = "arn:${data.aws_partition.current.partition}:ec2:*:*:security-group/*"
        Condition = { Null = { "aws:RequestTag/elbv2.k8s.aws/cluster" = "true", "aws:ResourceTag/elbv2.k8s.aws/cluster" = "false" } }
      },
      {
        Effect    = "Allow"
        Action    = ["ec2:AuthorizeSecurityGroupIngress", "ec2:RevokeSecurityGroupIngress", "ec2:DeleteSecurityGroup"]
        Resource  = "*"
        Condition = { Null = { "aws:ResourceTag/elbv2.k8s.aws/cluster" = "false" } }
      },
      {
        Effect    = "Allow"
        Action    = ["elasticloadbalancing:CreateLoadBalancer", "elasticloadbalancing:CreateTargetGroup"]
        Resource  = "*"
        Condition = { Null = { "aws:RequestTag/elbv2.k8s.aws/cluster" = "false" } }
      },
      {
        Effect   = "Allow"
        Action   = ["elasticloadbalancing:CreateListener", "elasticloadbalancing:DeleteListener", "elasticloadbalancing:CreateRule", "elasticloadbalancing:DeleteRule"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = ["elasticloadbalancing:AddTags", "elasticloadbalancing:RemoveTags"]
        Resource = [
          "arn:${data.aws_partition.current.partition}:elasticloadbalancing:*:*:targetgroup/*/*",
          "arn:${data.aws_partition.current.partition}:elasticloadbalancing:*:*:loadbalancer/net/*/*",
          "arn:${data.aws_partition.current.partition}:elasticloadbalancing:*:*:loadbalancer/app/*/*"
        ]
        Condition = { Null = { "aws:RequestTag/elbv2.k8s.aws/cluster" = "true", "aws:ResourceTag/elbv2.k8s.aws/cluster" = "false" } }
      },
      {
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:ModifyLoadBalancerAttributes", "elasticloadbalancing:SetIpAddressType",
          "elasticloadbalancing:SetSecurityGroups", "elasticloadbalancing:SetSubnets", "elasticloadbalancing:DeleteLoadBalancer",
          "elasticloadbalancing:ModifyTargetGroup", "elasticloadbalancing:ModifyTargetGroupAttributes",
          "elasticloadbalancing:DeleteTargetGroup", "elasticloadbalancing:ModifyListenerAttributes"
        ]
        Resource  = "*"
        Condition = { Null = { "aws:ResourceTag/elbv2.k8s.aws/cluster" = "false" } }
      },
      {
        Effect = "Allow"
        Action = ["elasticloadbalancing:AddTags"]
        Resource = [
          "arn:${data.aws_partition.current.partition}:elasticloadbalancing:*:*:targetgroup/*/*",
          "arn:${data.aws_partition.current.partition}:elasticloadbalancing:*:*:loadbalancer/net/*/*",
          "arn:${data.aws_partition.current.partition}:elasticloadbalancing:*:*:loadbalancer/app/*/*"
        ]
        Condition = { StringEquals = { "elasticloadbalancing:CreateAction" = ["CreateTargetGroup", "CreateLoadBalancer"] }, Null = { "aws:RequestTag/elbv2.k8s.aws/cluster" = "false" } }
      },
      {
        Effect   = "Allow"
        Action   = ["elasticloadbalancing:RegisterTargets", "elasticloadbalancing:DeregisterTargets"]
        Resource = "arn:${data.aws_partition.current.partition}:elasticloadbalancing:*:*:targetgroup/*/*"
      },
      {
        Effect   = "Allow"
        Action   = ["elasticloadbalancing:ModifyListener", "elasticloadbalancing:AddListenerCertificates", "elasticloadbalancing:RemoveListenerCertificates", "elasticloadbalancing:ModifyRule", "elasticloadbalancing:SetRulePriorities"]
        Resource = "*"
      }
    ]
  }
}

data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_sesv2_email_identity" "notifications" {
  count          = var.create_ses_identity ? 1 : 0
  email_identity = var.domain_name
  tags           = var.tags

  dkim_signing_attributes {
    next_signing_key_length = "RSA_2048_BIT"
  }
}

resource "aws_route53_record" "ses_dkim" {
  for_each = var.create_ses_identity ? toset(aws_sesv2_email_identity.notifications[0].dkim_signing_attributes[0].tokens) : toset([])

  zone_id = var.route53_zone_id
  name    = "${each.value}._domainkey.${var.domain_name}"
  type    = "CNAME"
  ttl     = 300
  records = ["${each.value}.dkim.amazonses.com"]
}

resource "aws_acm_certificate" "storefront" {
  domain_name       = var.domain_name
  validation_method = "DNS"
  tags              = var.tags
}

resource "aws_route53_record" "certificate_validation" {
  for_each = {
    for option in aws_acm_certificate.storefront.domain_validation_options : option.domain_name => {
      name   = option.resource_record_name
      record = option.resource_record_value
      type   = option.resource_record_type
    }
  }

  zone_id         = var.route53_zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "storefront" {
  certificate_arn         = aws_acm_certificate.storefront.arn
  validation_record_fqdns = [for record in aws_route53_record.certificate_validation : record.fqdn]
}

module "load_balancer_controller_role" {
  source             = "../irsa-role"
  name               = "${var.name}-aws-load-balancer-controller"
  policy_name        = "manage-ingress-load-balancers"
  oidc_provider_arn  = var.oidc_provider_arn
  oidc_issuer_url    = var.oidc_issuer_url
  namespace          = "kube-system"
  service_account    = "aws-load-balancer-controller"
  permissions_policy = local.load_balancer_controller_policy
  tags               = var.tags
}

module "external_dns_role" {
  source            = "../irsa-role"
  name              = "${var.name}-external-dns"
  policy_name       = "manage-storefront-dns-records"
  oidc_provider_arn = var.oidc_provider_arn
  oidc_issuer_url   = var.oidc_issuer_url
  namespace         = "kube-system"
  service_account   = "external-dns"
  tags              = var.tags
  permissions_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["route53:ChangeResourceRecordSets", "route53:ListResourceRecordSets", "route53:ListTagsForResources"]
        Resource = local.zone_arn
      },
      {
        Effect   = "Allow"
        Action   = ["route53:ListHostedZones"]
        Resource = "*"
      }
    ]
  }
}

moved {
  from = aws_iam_role.load_balancer_controller
  to   = module.load_balancer_controller_role.aws_iam_role.this
}

moved {
  from = aws_iam_role_policy.load_balancer_controller
  to   = module.load_balancer_controller_role.aws_iam_role_policy.this
}

moved {
  from = aws_iam_role.external_dns
  to   = module.external_dns_role.aws_iam_role.this
}

moved {
  from = aws_iam_role_policy.external_dns
  to   = module.external_dns_role.aws_iam_role_policy.this
}

output "certificate_arn" { value = aws_acm_certificate_validation.storefront.certificate_arn }
output "ses_identity_arn" {
  value = "arn:${data.aws_partition.current.partition}:ses:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:identity/${var.domain_name}"
}
output "ses_from_address" { value = var.create_ses_identity ? "orders@${var.domain_name}" : "" }
output "load_balancer_controller_role_arn" { value = module.load_balancer_controller_role.arn }
output "external_dns_role_arn" { value = module.external_dns_role.arn }
