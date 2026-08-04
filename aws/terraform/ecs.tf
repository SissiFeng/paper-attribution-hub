# ---------------------------------------------------------------------------
# ECS — Fargate cluster, task definition, service, and auto-scaling
# ---------------------------------------------------------------------------

resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.common_tags
}

# --- Task Definition ---

resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.name_prefix}-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.backend_cpu
  memory                   = var.backend_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "backend"
      image = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      # Environment variables from plain text
      environment = [
        { name = "PAS_DATABASE_URL", value = local.db_connection_url },
        { name = "PAS_CORS_ORIGINS", value = jsonencode(var.cors_origins) },
        { name = "PAS_S3_ARTIFACTS_BUCKET", value = aws_s3_bucket.artifacts.id },
        { name = "PAS_AWS_REGION", value = var.aws_region },
        { name = "PAS_KIMI_MODEL", value = var.kimi_model },
        { name = "PAS_ACTIVE_LEARNING", value = "1" },
        { name = "PAS_ACTIVE_RETRAIN_EVERY", value = tostring(var.active_retrain_every) },
        { name = "PAS_MODEL_AUTO_PROMOTE", value = tostring(var.model_auto_promote) },
        { name = "PAS_BUILD_REVISION", value = var.image_tag },
      ]

      # Secrets from SSM Parameter Store (injected by ECS agent at startup)
      secrets = [
        { name = "PAS_ANTHROPIC_API_KEY", valueFrom = aws_ssm_parameter.anthropic_api_key.arn },
        { name = "PAS_KIMI_API_KEY", valueFrom = aws_ssm_parameter.kimi_api_key.arn },
        { name = "PAS_SEMANTIC_SCHOLAR_API_KEY", valueFrom = aws_ssm_parameter.semantic_scholar_api_key.arn },
        { name = "PAS_OPENALEX_MAILTO", valueFrom = aws_ssm_parameter.openalex_mailto.arn },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.backend.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "backend"
        }
      }

      # Health check for ECS container-level monitoring (separate from ALB health check)
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 120 # allow time for alembic + data seeding
      }
    }
  ])
}

# --- Service ---

resource "aws_ecs_service" "backend" {
  name            = "${local.name_prefix}-backend-svc"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.backend_desired_count
  launch_type     = "FARGATE"

  # Rolling update: keep at least 1 healthy task during deploy
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 300

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  depends_on = [
    aws_lb_listener.http,
    aws_lb_listener.https,
    aws_db_instance.main,
  ]

  tags = local.common_tags
}

# --- Auto-Scaling ---

resource "aws_appautoscaling_target" "backend" {
  max_capacity       = 4
  min_capacity       = var.backend_desired_count
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "backend_cpu" {
  name               = "${local.name_prefix}-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.backend.resource_id
  scalable_dimension = aws_appautoscaling_target.backend.scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
