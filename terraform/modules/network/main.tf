data "aws_availability_zones" "available" { state = "available" }

variable "name" { type = string }
variable "vpc_cidr" { type = string }
variable "enable_nat_gateway" { type = bool }

module "vpc" {
  source               = "terraform-aws-modules/vpc/aws"
  version              = "~> 6.0"
  name                 = var.name
  cidr                 = var.vpc_cidr
  azs                  = slice(data.aws_availability_zones.available.names, 0, 3)
  private_subnets      = [for index in range(3) : cidrsubnet(var.vpc_cidr, 8, index + 1)]
  public_subnets       = [for index in range(3) : cidrsubnet(var.vpc_cidr, 8, index + 101)]
  enable_nat_gateway   = var.enable_nat_gateway
  single_nat_gateway   = true
  enable_dns_hostnames = true
  enable_dns_support   = true
  public_subnet_tags   = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags  = { "kubernetes.io/role/internal-elb" = 1 }
}

output "vpc_id" { value = module.vpc.vpc_id }
output "private_subnets" { value = module.vpc.private_subnets }
output "public_subnets" { value = module.vpc.public_subnets }
