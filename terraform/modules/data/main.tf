variable "name" { type = string }
variable "tags" { type = map(string) }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "eks_cluster_security_group_id" { type = string }

resource "aws_security_group" "data" {
  name        = "${var.name}-data"
  # Preserve the existing description: changing it replaces the RDS-attached group.
  description = "Private access to the dev database and cache from EKS nodes"
  vpc_id      = var.vpc_id
  tags        = var.tags
}

resource "aws_vpc_security_group_ingress_rule" "mysql_from_eks" {
  security_group_id            = aws_security_group.data.id
  referenced_security_group_id = var.eks_cluster_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  description                  = "MySQL from EKS Fargate pods"
  tags                         = var.tags
}

resource "aws_vpc_security_group_ingress_rule" "valkey_from_eks" {
  security_group_id            = aws_security_group.data.id
  referenced_security_group_id = var.eks_cluster_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
  description                  = "Valkey from EKS Fargate pods"
  tags                         = var.tags
}

resource "aws_dynamodb_table" "inventory" {
  name         = "${var.name}-inventory"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "sku"
  tags         = var.tags
  attribute {
    name = "sku"
    type = "S"
  }
}

resource "aws_db_subnet_group" "mysql" {
  name       = "${var.name}-mysql"
  subnet_ids = var.private_subnet_ids
  tags       = var.tags
}

resource "aws_db_instance" "mysql" {
  identifier                  = "${var.name}-mysql"
  engine                      = "mysql"
  engine_version              = "8.0"
  instance_class              = "db.t3.micro"
  allocated_storage           = 20
  max_allocated_storage       = 30
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = "retail"
  username                    = "retail_admin"
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.mysql.name
  vpc_security_group_ids      = [aws_security_group.data.id]
  publicly_accessible         = false
  multi_az                    = false
  backup_retention_period     = 1
  auto_minor_version_upgrade  = true
  deletion_protection         = false
  skip_final_snapshot         = true
  apply_immediately           = true
  tags                        = var.tags
}

resource "aws_elasticache_serverless_cache" "valkey" {
  name                     = substr(replace("${var.name}-valkey", "_", "-"), 0, 40)
  description              = "Dev cache for product catalog reads"
  engine                   = "valkey"
  major_engine_version     = "8"
  subnet_ids               = var.private_subnet_ids
  security_group_ids       = [aws_security_group.data.id]
  daily_snapshot_time      = null
  snapshot_retention_limit = 0
  tags                     = var.tags

  cache_usage_limits {
    data_storage {
      maximum = 1
      unit    = "GB"
    }
    ecpu_per_second {
      maximum = 1000
    }
  }
}

output "inventory_table_name" { value = aws_dynamodb_table.inventory.name }
output "inventory_table_arn" { value = aws_dynamodb_table.inventory.arn }
output "mysql_endpoint" { value = aws_db_instance.mysql.address }
output "mysql_port" { value = aws_db_instance.mysql.port }
output "mysql_database_name" { value = aws_db_instance.mysql.db_name }
output "mysql_master_secret_arn" { value = aws_db_instance.mysql.master_user_secret[0].secret_arn }
output "valkey_endpoint" { value = aws_elasticache_serverless_cache.valkey.endpoint[0].address }
output "valkey_port" { value = aws_elasticache_serverless_cache.valkey.endpoint[0].port }
