# ---------------------------------------------------------------------------
# CloudWatch — Log groups, alarms
# ---------------------------------------------------------------------------

# --- Backend application logs ---

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${local.name_prefix}-backend"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

# --- CPU utilization alarm ---

resource "aws_cloudwatch_metric_alarm" "backend_cpu_high" {
  alarm_name          = "${local.name_prefix}-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 85
  alarm_description   = "Backend service CPU > 85% for 3 minutes"
  alarm_actions       = [] # Add SNS topic ARN for email/chat notifications

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.backend.name
  }

  tags = local.common_tags
}

# --- Memory utilization alarm ---

resource "aws_cloudwatch_metric_alarm" "backend_memory_high" {
  alarm_name          = "${local.name_prefix}-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 85
  alarm_description   = "Backend service memory > 85% for 3 minutes"
  alarm_actions       = [] # Add SNS topic ARN for email/chat notifications

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.backend.name
  }

  tags = local.common_tags
}

# --- RDS CPU alarm ---

resource "aws_cloudwatch_metric_alarm" "rds_cpu_high" {
  alarm_name          = "${local.name_prefix}-rds-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 60
  statistic           = "Average"
  threshold           = 85
  alarm_description   = "RDS database CPU > 85% for 3 minutes"
  alarm_actions       = [] # Add SNS topic ARN for email/chat notifications

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.identifier
  }

  tags = local.common_tags
}

# --- RDS free storage alarm ---

resource "aws_cloudwatch_metric_alarm" "rds_storage_low" {
  alarm_name          = "${local.name_prefix}-rds-storage-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 5 * 1024 * 1024 * 1024 # 5 GB
  alarm_description   = "RDS free storage < 5 GB"
  alarm_actions       = [] # Add SNS topic ARN for email/chat notifications

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.identifier
  }

  tags = local.common_tags
}
