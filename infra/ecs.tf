# ─────────────────────────────────────────────
# ECS Cluster
# ─────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "doctor-agent-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.common_tags
}

# ─────────────────────────────────────────────
# CloudWatch Log Groups
# ─────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/doctor-agent"
  retention_in_days = 7
  tags              = local.common_tags
}

# The unified container logs everything to /ecs/doctor-agent (aws_cloudwatch_log_group.ecs)

# ─────────────────────────────────────────────
# ECS Task Definition — Backend
# ─────────────────────────────────────────────

resource "aws_ecs_task_definition" "backend" {
  family                   = "doctor-agent-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.ecs_cpu
  memory                   = var.ecs_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "backend"
      image = "${aws_ecr_repository.backend.repository_url}:latest"

      # nginx (the only external port) is configured via $PORT inside the container.
      # FastAPI runs on 8000 and Next.js on 3000 — both internal, not exposed.
      portMappings = [{
        containerPort = 80
        protocol      = "tcp"
      }]

      # ── Non-sensitive environment variables ───────────────────────────────
      environment = concat(
        [
          { name = "ENVIRONMENT",      value = "production" },
          { name = "DEBUG",            value = "false" },
          # nginx binds to $PORT — set to 80 so ALB can reach it
          { name = "PORT",             value = "80" },
          { name = "DATABASE_BACKEND", value = "postgres" },
          { name = "AWS_REGION",       value = var.aws_region },
          { name = "APP_URL",          value = var.app_url },
          {
            name  = "CORS_ORIGINS"
            value = var.enable_alb ? "https://${aws_lb.main[0].dns_name}" : "*"
          },
          { name = "MESSAGE_TTL_HOURS",               value = "48" },
          { name = "SECRETS_MANAGER_OPENAI_KEY_NAME", value = aws_secretsmanager_secret.openai.name },
        ],
        # Storage backend — set to S3 when the media bucket is enabled
        var.enable_s3 ? [
          { name = "STORAGE_BACKEND", value = "s3" },
          { name = "S3_BUCKET_NAME",  value = var.s3_media_bucket_name },
          { name = "S3_REGION",       value = var.aws_region },
        ] : [
          { name = "STORAGE_BACKEND", value = "cloudinary" },
        ]
      )

      # ── Sensitive values — fetched from Secrets Manager at startup ────────
      # ECS resolves each ARN and injects the plain-text value as an env var.
      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = aws_secretsmanager_secret.database_url.arn
        },
        {
          name      = "SECRET_ENCRYPTION_KEY"
          valueFrom = aws_secretsmanager_secret.secret_encryption_key.arn
        },
        {
          name      = "JWT_SECRET_KEY"
          valueFrom = aws_secretsmanager_secret.jwt_secret_key.arn
        },
        {
          name      = "OPENAI_API_KEY"
          valueFrom = aws_secretsmanager_secret.openai.arn
        },
        {
          name      = "INSTAGRAM_WEBHOOK_VERIFY_TOKEN"
          valueFrom = aws_secretsmanager_secret.instagram_webhook_verify_token.arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      # Health check goes through nginx (/health is proxied to FastAPI)
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:80/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 120  # Unified container starts 3 processes; allow extra time
      }
    }
  ])

  tags = local.common_tags
}

# ─────────────────────────────────────────────
# ECS Service — Backend
# ─────────────────────────────────────────────

resource "aws_ecs_service" "backend" {
  name            = "doctor-agent-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.ecs_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.ecs_service.id]
    # Tasks stay private when ALB is enabled; need a public IP otherwise (for outbound internet)
    assign_public_ip = !var.enable_alb
  }

  dynamic "load_balancer" {
    for_each = var.enable_alb ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.backend[0].arn
      container_name   = "backend"
      container_port   = 80
    }
  }

  depends_on = [
    aws_iam_role_policy.ecs_execution,
    aws_iam_role_policy.ecs_task,
    # RDS must be available before the app starts
    aws_db_instance.main,
  ]

  tags = local.common_tags
}
