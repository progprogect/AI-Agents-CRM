# ─────────────────────────────────────────────
# IAM Role: ECS Task Execution
# Grants ECS the ability to pull images from ECR and write logs to CloudWatch.
# Also allows fetching secrets from Secrets Manager at container startup.
# ─────────────────────────────────────────────

resource "aws_iam_role" "ecs_execution" {
  name = "doctor-agent-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "ecs_execution" {
  name = "doctor-agent-ecs-execution-policy"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Pull Docker images from ECR
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      },
      # Write logs to CloudWatch (unified container logs to /ecs/doctor-agent)
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = ["${aws_cloudwatch_log_group.ecs.arn}:*"]
      },
      # Fetch secrets at container startup (injected as env vars via ECS secrets[])
      {
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = [
          aws_secretsmanager_secret.openai.arn,
          aws_secretsmanager_secret.instagram_webhook_verify_token.arn,
          aws_secretsmanager_secret.database_url.arn,
          aws_secretsmanager_secret.secret_encryption_key.arn,
          aws_secretsmanager_secret.jwt_secret_key.arn,
        ]
      }
    ]
  })
}

# ─────────────────────────────────────────────
# IAM Role: ECS Task (application runtime)
# Grants the running container permissions to call AWS services.
# With Postgres backend: only Secrets Manager access is needed at runtime
# (for creating/updating channel token secrets via the admin UI).
# ─────────────────────────────────────────────

resource "aws_iam_role" "ecs_task" {
  name = "doctor-agent-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "ecs_task" {
  name = "doctor-agent-ecs-task-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Read the OpenAI key at runtime (LLM factory reads it on demand)
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [aws_secretsmanager_secret.openai.arn]
      },
      # Create/update/delete channel and notification token secrets via admin UI.
      # The app stores encrypted tokens in Postgres but also optionally uses
      # Secrets Manager for fine-grained per-binding secrets.
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:CreateSecret",
          "secretsmanager:UpdateSecret",
          "secretsmanager:DeleteSecret",
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:*:secret:doctor-agent/channels/*",
          "arn:aws:secretsmanager:${var.aws_region}:*:secret:doctor-agent/channels/*-*",
          "arn:aws:secretsmanager:${var.aws_region}:*:secret:doctor-agent/notifications/*",
          "arn:aws:secretsmanager:${var.aws_region}:*:secret:doctor-agent/notifications/*-*"
        ]
      }
    ]
  })
}
