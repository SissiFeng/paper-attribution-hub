# ---------------------------------------------------------------------------
# Scheduled ETL, Zotero Markdown ingestion, and model evolution
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${local.name_prefix}-worker"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name_prefix}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  ephemeral_storage {
    size_in_gib = var.worker_ephemeral_storage
  }

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"
      essential = true
      command   = ["python", "-m", "app.scripts.run_model_evolution", "--json"]

      environment = [
        { name = "PAS_DATABASE_URL", value = local.db_connection_url },
        { name = "PAS_S3_ARTIFACTS_BUCKET", value = aws_s3_bucket.artifacts.id },
        { name = "PAS_AWS_REGION", value = var.aws_region },
        { name = "PAS_KIMI_MODEL", value = var.kimi_model },
        { name = "PAS_ACTIVE_LEARNING", value = var.sdl_stage1_only || !var.active_learning_enabled ? "0" : "1" },
        { name = "PAS_ACTIVE_RETRAIN_EVERY", value = tostring(var.active_retrain_every) },
        { name = "PAS_MODEL_AUTO_PROMOTE", value = tostring(var.model_auto_promote) },
        { name = "PAS_BUILD_REVISION", value = var.image_tag },
        { name = "PAS_PIPELINE_DISCOVERY", value = tostring(var.pipeline_discovery) },
        { name = "PAS_PIPELINE_FULLTEXT", value = tostring(var.pipeline_fulltext) },
        { name = "PAS_ZOTERO_GROUP_ID", value = var.zotero_group_id },
        { name = "PAS_ZOTERO_TIER1_COLLECTION", value = var.zotero_tier1_collection },
        { name = "PAS_ZOTERO_TIER2_COLLECTION", value = var.zotero_tier2_collection },
        { name = "PAS_ZOTERO_DOWNLOAD_FULLTEXTS", value = "false" },
        { name = "PAS_ZOTERO_SOURCE_ONLY", value = tostring(var.zotero_source_only) },
        { name = "PAS_SDL_STAGE1_ONLY", value = tostring(var.sdl_stage1_only) },
        { name = "PAS_SDL_STAGE1_TRAINING_THROUGH_ROUND", value = "0" },
        { name = "PAS_SDL_STAGE1_DESCRIPTIVE_ANALYTICS_ENABLED", value = tostring(var.sdl_stage1_descriptive_analytics_enabled) },
        { name = "PAS_LEARNED_CLASSIFIER", value = var.sdl_stage1_only || !var.learned_classifier_enabled ? "0" : "1" },
      ]

      secrets = [
        { name = "PAS_ANTHROPIC_API_KEY", valueFrom = aws_ssm_parameter.anthropic_api_key.arn },
        { name = "PAS_KIMI_API_KEY", valueFrom = aws_ssm_parameter.kimi_api_key.arn },
        { name = "PAS_SEMANTIC_SCHOLAR_API_KEY", valueFrom = aws_ssm_parameter.semantic_scholar_api_key.arn },
        { name = "PAS_OPENALEX_MAILTO", valueFrom = aws_ssm_parameter.openalex_mailto.arn },
        { name = "PAS_ZOTERO_API_KEY", valueFrom = aws_ssm_parameter.zotero_api_key.arn },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.worker.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "worker"
        }
      }

      stopTimeout = 120
    }
  ])
}

resource "aws_sqs_queue" "worker_failures" {
  name                      = "${local.name_prefix}-worker-failures"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  tags                      = local.common_tags
}

resource "aws_iam_role" "eventbridge_worker" {
  name = "${local.name_prefix}-eventbridge-worker"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy" "eventbridge_worker" {
  name = "${local.name_prefix}-eventbridge-worker"
  role = aws_iam_role.eventbridge_worker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecs:RunTask"
        Resource = "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task-definition/${local.name_prefix}-worker:*"
        Condition = {
          ArnEquals = {
            "ecs:cluster" = aws_ecs_cluster.main.arn
          }
        }
      },
      {
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          aws_iam_role.ecs_execution.arn,
          aws_iam_role.ecs_task.arn,
        ]
      },
    ]
  })
}

resource "aws_cloudwatch_event_rule" "model_evolution" {
  name                = "${local.name_prefix}-model-evolution"
  description         = "Drain complete human-review retraining batches"
  schedule_expression = var.model_evolution_schedule
  state               = var.worker_schedules_enabled && !var.sdl_stage1_only ? "ENABLED" : "DISABLED"
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_rule" "daily_pipeline" {
  name                = "${local.name_prefix}-daily-pipeline"
  description         = "Run incremental classification and staged screening"
  schedule_expression = var.pipeline_schedule
  state               = var.worker_schedules_enabled ? "ENABLED" : "DISABLED"
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "model_evolution" {
  rule     = aws_cloudwatch_event_rule.model_evolution.name
  arn      = aws_ecs_cluster.main.arn
  role_arn = aws_iam_role.eventbridge_worker.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.worker.arn
    launch_type         = "FARGATE"
    platform_version    = "LATEST"
    task_count          = 1

    network_configuration {
      subnets          = aws_subnet.private[*].id
      security_groups  = [aws_security_group.worker.id]
      assign_public_ip = false
    }
  }

  input = jsonencode({
    containerOverrides = [{
      name    = "worker"
      command = ["python", "-m", "app.scripts.run_model_evolution", "--json"]
    }]
  })

  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 2
  }

  dead_letter_config {
    arn = aws_sqs_queue.worker_failures.arn
  }

  depends_on = [aws_sqs_queue_policy.worker_failures]
}

resource "aws_cloudwatch_event_target" "daily_pipeline" {
  rule     = aws_cloudwatch_event_rule.daily_pipeline.name
  arn      = aws_ecs_cluster.main.arn
  role_arn = aws_iam_role.eventbridge_worker.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.worker.arn
    launch_type         = "FARGATE"
    platform_version    = "LATEST"
    task_count          = 1

    network_configuration {
      subnets          = aws_subnet.private[*].id
      security_groups  = [aws_security_group.worker.id]
      assign_public_ip = false
    }
  }

  input = jsonencode({
    containerOverrides = [{
      name = "worker"
      command = concat(
        ["python", "-m", "app.scripts.run_daily_pipeline"],
        var.sdl_stage1_only ? [] : ["--learned"],
        ["--triggered-by", "eventbridge", "--json"],
      )
    }]
  })

  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 2
  }

  dead_letter_config {
    arn = aws_sqs_queue.worker_failures.arn
  }

  depends_on = [aws_sqs_queue_policy.worker_failures]
}

# S3 emits EventBridge events, but only a complete batch marker starts ETL.
resource "aws_s3_bucket_notification" "artifacts_eventbridge" {
  bucket      = aws_s3_bucket.artifacts.id
  eventbridge = true
}

resource "aws_cloudwatch_event_rule" "zotero_markdown_batch" {
  name        = "${local.name_prefix}-zotero-markdown-batch"
  description = "Start import only after explicit Zotero Markdown ETL promotion"
  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = {
        name = [aws_s3_bucket.artifacts.id]
      }
      object = {
        key = [{
          wildcard = "manifests/zotero/etl-ready/*/batch-manifest.json"
        }]
      }
    }
  })
  tags = local.common_tags
}

resource "aws_cloudwatch_event_target" "zotero_markdown_batch" {
  rule     = aws_cloudwatch_event_rule.zotero_markdown_batch.name
  arn      = aws_ecs_cluster.main.arn
  role_arn = aws_iam_role.eventbridge_worker.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.worker.arn
    launch_type         = "FARGATE"
    platform_version    = "LATEST"
    task_count          = 1

    network_configuration {
      subnets          = aws_subnet.private[*].id
      security_groups  = [aws_security_group.worker.id]
      assign_public_ip = false
    }
  }

  input_transformer {
    input_paths = {
      manifest_key = "$.detail.object.key"
    }
    input_template = <<-JSON
      {"containerOverrides":[{"name":"worker","command":["python","-m","app.scripts.run_zotero_markdown_etl","--manifest-key",<manifest_key>,"--json"]}]}
    JSON
  }

  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 2
  }

  dead_letter_config {
    arn = aws_sqs_queue.worker_failures.arn
  }

  depends_on = [
    aws_s3_bucket_notification.artifacts_eventbridge,
    aws_sqs_queue_policy.worker_failures,
  ]
}

resource "aws_cloudwatch_event_rule" "worker_failed" {
  name        = "${local.name_prefix}-worker-failed"
  description = "Capture non-zero scheduled worker exits"
  event_pattern = jsonencode({
    source        = ["aws.ecs"]
    "detail-type" = ["ECS Task State Change"]
    detail = {
      clusterArn        = [aws_ecs_cluster.main.arn]
      taskDefinitionArn = [{ prefix = "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task-definition/${local.name_prefix}-worker:" }]
      lastStatus        = ["STOPPED"]
      containers = {
        exitCode = [{ "anything-but" = 0 }]
      }
    }
  })
  tags = local.common_tags
}

resource "aws_cloudwatch_event_target" "worker_failed" {
  rule       = aws_cloudwatch_event_rule.worker_failed.name
  target_id  = "worker-failure-queue"
  arn        = aws_sqs_queue.worker_failures.arn
  depends_on = [aws_sqs_queue_policy.worker_failures]
}

resource "aws_cloudwatch_event_rule" "worker_failed_to_start" {
  name        = "${local.name_prefix}-worker-failed-to-start"
  description = "Capture scheduled workers that ECS could not start"
  event_pattern = jsonencode({
    source        = ["aws.ecs"]
    "detail-type" = ["ECS Task State Change"]
    detail = {
      clusterArn        = [aws_ecs_cluster.main.arn]
      taskDefinitionArn = [{ prefix = "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task-definition/${local.name_prefix}-worker:" }]
      lastStatus        = ["STOPPED"]
      stopCode          = ["TaskFailedToStart"]
    }
  })
  tags = local.common_tags
}

resource "aws_cloudwatch_event_target" "worker_failed_to_start" {
  rule       = aws_cloudwatch_event_rule.worker_failed_to_start.name
  target_id  = "worker-start-failure-queue"
  arn        = aws_sqs_queue.worker_failures.arn
  depends_on = [aws_sqs_queue_policy.worker_failures]
}

resource "aws_sqs_queue_policy" "worker_failures" {
  queue_url = aws_sqs_queue.worker_failures.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowEventBridgeWorkerFailures"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.worker_failures.arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = [
            aws_cloudwatch_event_rule.model_evolution.arn,
            aws_cloudwatch_event_rule.daily_pipeline.arn,
            aws_cloudwatch_event_rule.zotero_markdown_batch.arn,
            aws_cloudwatch_event_rule.worker_failed.arn,
            aws_cloudwatch_event_rule.worker_failed_to_start.arn,
          ]
        }
      }
    }]
  })
}

resource "aws_cloudwatch_metric_alarm" "worker_failures" {
  alarm_name          = "${local.name_prefix}-worker-failures"
  alarm_description   = "A scheduled task could not start or exited non-zero"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.worker_failures.name
  }

  tags = local.common_tags
}
