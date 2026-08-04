# ---------------------------------------------------------------------------
# RDS PostgreSQL 16 with pgvector
# ---------------------------------------------------------------------------

# --- DB Subnet Group ---

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnet"
  subnet_ids = aws_subnet.private[*].id

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-db-subnet" })
}

# --- Parameter Group (pgvector + pg_stat_statements) ---

resource "aws_db_parameter_group" "pgvector" {
  name   = "${local.name_prefix}-pgvector-pg16"
  family = "postgres16"

  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements"
    apply_method = "pending-reboot"
  }

  tags = local.common_tags
}

# --- RDS Instance ---

resource "random_password" "db" {
  length  = 32
  special = false # avoid characters that need URL encoding
}

resource "aws_db_instance" "main" {
  identifier = "${local.name_prefix}-db"

  engine         = "postgres"
  engine_version = "16.4"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_encrypted     = true
  storage_type          = "gp3"

  db_name  = "paper_attribution"
  username = var.db_username != "" ? var.db_username : "pas_admin"
  password = var.db_password != "" ? var.db_password : random_password.db.result

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name
  parameter_group_name   = aws_db_parameter_group.pgvector.name

  # Backup & maintenance
  backup_retention_period = var.environment == "prod" ? 14 : 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  # Safety: prevent accidental deletion in production
  deletion_protection       = var.environment == "prod"
  skip_final_snapshot       = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${local.name_prefix}-db-final-${formatdate("YYYYMMDD-hhmmss", timestamp())}" : null

  # Monitoring
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  monitoring_interval             = 0

  # No public access — ECS communicates via private subnets
  publicly_accessible = false

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-db" })
}
