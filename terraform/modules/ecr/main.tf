variable "name" { type = string }
variable "services" { type = set(string) }
variable "tags" { type = map(string) }

resource "aws_ecr_repository" "service" {
  for_each             = var.services
  name                 = "${var.name}/${each.value}-service"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  tags                 = var.tags
  encryption_configuration {
    encryption_type = "AES256"
  }
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "service" {
  for_each   = aws_ecr_repository.service
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Retain the 40 most recent tagged release images"
      selection = {
        tagStatus      = "tagged"
        tagPatternList = ["*"]
        countType      = "imageCountMoreThan"
        countNumber    = 40
      }
      action = { type = "expire" }
    }]
  })
}

output "repository_urls" {
  value = { for name, repo in aws_ecr_repository.service : name => repo.repository_url }
}
