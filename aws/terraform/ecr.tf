# ---------------------------------------------------------------------------
# ECR — private Docker registry for the backend image
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "backend" {
  name                 = "${local.name_prefix}-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  force_delete = var.environment != "prod"

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-ecr" })
}

# Lifecycle policy: keep last 10 images, expire untagged images after 7 days
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images older than 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep maximum 10 tagged images"
        selection = {
          tagStatus   = "tagged"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}
