variable "name" { type = string }
variable "services" { type = set(string) }

resource "aws_ecr_repository" "service" {
  for_each             = var.services
  name                 = "${var.name}/${each.value}-service"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true
  image_scanning_configuration { scan_on_push = true }
}

output "repository_urls" {
  value = { for name, repo in aws_ecr_repository.service : name => repo.repository_url }
}
