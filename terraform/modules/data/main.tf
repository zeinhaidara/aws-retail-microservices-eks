variable "name" { type = string }

resource "aws_dynamodb_table" "inventory" {
  name         = "${var.name}-inventory"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "sku"
  attribute {
    name = "sku"
    type = "S"
  }
}

output "inventory_table_name" { value = aws_dynamodb_table.inventory.name }
