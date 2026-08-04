# ---------------------------------------------------------------------------
# Security Groups — layered approach
#   ALB-SG:  allows 443 + 80 from internet
#   ECS-SG:  allows 8000 from ALB-SG only
#   RDS-SG:  allows 5432 from ECS-SG only
#   VPCE-SG: allows HTTPS from ECS-SG (for VPC endpoints)
# ---------------------------------------------------------------------------

# --- ALB ---
resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb-sg"
  description = "Application Load Balancer"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP from internet (redirect to HTTPS)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-alb-sg" })
}

# --- ECS ---
resource "aws_security_group" "ecs" {
  name        = "${local.name_prefix}-ecs-sg"
  description = "ECS Fargate tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Backend port from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "All outbound (NAT for internet, VPC endpoints for AWS APIs)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-ecs-sg" })
}

# --- RDS ---
resource "aws_security_group" "rds" {
  name        = "${local.name_prefix}-rds-sg"
  description = "RDS PostgreSQL"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from ECS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-rds-sg" })
}

# --- VPC Endpoints ---
resource "aws_security_group" "vpc_endpoints" {
  name        = "${local.name_prefix}-vpce-sg"
  description = "VPC Endpoints"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "HTTPS from ECS"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-vpce-sg" })
}
