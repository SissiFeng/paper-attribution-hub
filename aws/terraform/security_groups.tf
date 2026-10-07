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

# --- Scheduled workers ---
resource "aws_security_group" "worker" {
  name        = "${local.name_prefix}-worker-sg"
  description = "Scheduled Fargate ETL and model-evolution tasks"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "Database, AWS APIs, and optional discovery APIs"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-worker-sg" })
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

  lifecycle {
    # Worker access is managed by aws_vpc_security_group_ingress_rule.rds_worker.
    # Ignore provider normalization that folds that standalone rule into this
    # legacy inline ingress block and would otherwise try to revoke it.
    ignore_changes = [ingress]
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

  lifecycle {
    # Worker access is managed by
    # aws_vpc_security_group_ingress_rule.vpc_endpoints_worker.
    ignore_changes = [ingress]
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-vpce-sg" })
}

resource "aws_vpc_security_group_ingress_rule" "rds_worker" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.worker.id
  description                  = "PostgreSQL from scheduled workers"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "vpc_endpoints_worker" {
  security_group_id            = aws_security_group.vpc_endpoints.id
  referenced_security_group_id = aws_security_group.worker.id
  description                  = "HTTPS from scheduled workers"
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
}
