provider "aws" {
  region = var.aws_region
}

# Validation: public_subnet_ids required when ALB is enabled
locals {
  _validation_public_subnets = var.enable_alb && length(var.public_subnet_ids) == 0 ? tobool("ERROR: public_subnet_ids must be provided when enable_alb is true") : true
}

# ─────────────────────────────────────────────
# Security Groups
# ─────────────────────────────────────────────

resource "aws_security_group" "ecs_service" {
  name        = "doctor-agent-ecs-service-sg"
  description = "ECS tasks — allow all outbound (internet for OpenAI, etc.)"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "doctor-agent-ecs-service-sg" })
}

# Redis security group — allow access from ECS tasks
resource "aws_security_group" "redis" {
  name        = "doctor-agent-redis-sg"
  description = "Allow Redis access only from ECS tasks"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis from ECS"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_service.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "doctor-agent-redis-sg" })
}

# ─────────────────────────────────────────────
# Secrets Manager — OpenAI API key
# (Separate from rds.tf secrets for clarity)
# ─────────────────────────────────────────────

resource "aws_secretsmanager_secret" "openai" {
  name        = "doctor-agent/openai-api-key"
  description = "OpenAI API key for Doctor Agent"
  tags        = local.common_tags
}

# Note: Set the actual secret value via AWS Console or CLI after terraform apply:
#   aws secretsmanager put-secret-value \
#     --secret-id doctor-agent/openai-api-key \
#     --secret-string "sk-..."

# ─────────────────────────────────────────────
# Secrets Manager — Instagram webhook token
# ─────────────────────────────────────────────

resource "aws_secretsmanager_secret" "instagram_webhook_verify_token" {
  name        = "doctor-agent/instagram-webhook-verify-token"
  description = "Instagram webhook verification token"
  tags        = local.common_tags
}
