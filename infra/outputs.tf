# ─────────────────────────────────────────────
# Networking
# ─────────────────────────────────────────────

output "ecs_service_sg_id" {
  description = "Security Group ID for ECS tasks"
  value       = aws_security_group.ecs_service.id
}

output "redis_sg_id" {
  description = "Security Group ID for ElastiCache Redis"
  value       = aws_security_group.redis.id
}

output "rds_sg_id" {
  description = "Security Group ID for RDS PostgreSQL"
  value       = aws_security_group.rds.id
}

# ─────────────────────────────────────────────
# RDS / PostgreSQL
# ─────────────────────────────────────────────

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (host only, without port)"
  value       = aws_db_instance.main.address
}

output "rds_port" {
  description = "RDS PostgreSQL port"
  value       = aws_db_instance.main.port
}

output "rds_database_name" {
  description = "PostgreSQL database name"
  value       = aws_db_instance.main.db_name
}

output "rds_identifier" {
  description = "RDS instance identifier"
  value       = aws_db_instance.main.identifier
}

# ─────────────────────────────────────────────
# Secrets Manager ARNs
# (use these to reference secrets in CI/CD or other Terraform modules)
# ─────────────────────────────────────────────

output "secret_database_url_arn" {
  description = "ARN of the DATABASE_URL secret in Secrets Manager"
  value       = aws_secretsmanager_secret.database_url.arn
}

output "secret_encryption_key_arn" {
  description = "ARN of the SECRET_ENCRYPTION_KEY secret in Secrets Manager"
  value       = aws_secretsmanager_secret.secret_encryption_key.arn
}

output "secret_jwt_key_arn" {
  description = "ARN of the JWT_SECRET_KEY secret in Secrets Manager"
  value       = aws_secretsmanager_secret.jwt_secret_key.arn
}

output "openai_secret_arn" {
  description = "ARN of the OpenAI API key secret in Secrets Manager"
  value       = aws_secretsmanager_secret.openai.arn
}

output "instagram_webhook_verify_token_secret_arn" {
  description = "ARN of the Instagram webhook verify token secret"
  value       = aws_secretsmanager_secret.instagram_webhook_verify_token.arn
}

# ─────────────────────────────────────────────
# ECS / ECR
# ─────────────────────────────────────────────

output "ecr_repository_url" {
  description = "ECR repository URL for the backend image"
  value       = aws_ecr_repository.backend.repository_url
}

output "frontend_ecr_repository_url" {
  description = "ECR repository URL for the frontend image"
  value       = aws_ecr_repository.frontend.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

output "ecs_service_name" {
  description = "ECS backend service name"
  value       = aws_ecs_service.backend.name
}

output "frontend_ecs_service_name" {
  description = "ECS frontend service name (only when ALB is enabled)"
  value       = var.enable_alb ? aws_ecs_service.frontend[0].name : null
}

# ─────────────────────────────────────────────
# IAM
# ─────────────────────────────────────────────

output "iam_ecs_execution_role_arn" {
  description = "IAM role ARN for ECS task execution (ECR pull, log write, secret fetch)"
  value       = aws_iam_role.ecs_execution.arn
}

output "iam_ecs_task_role_arn" {
  description = "IAM role ARN for ECS task runtime (Secrets Manager access)"
  value       = aws_iam_role.ecs_task.arn
}

# ─────────────────────────────────────────────
# ALB
# ─────────────────────────────────────────────

output "alb_dns_name" {
  description = "ALB DNS name — use this to create a CNAME in your DNS provider"
  value       = var.enable_alb ? aws_lb.main[0].dns_name : null
}

output "alb_arn" {
  description = "ALB ARN"
  value       = var.enable_alb ? aws_lb.main[0].arn : null
}

output "frontend_url" {
  description = "Frontend URL (via ALB, when enabled)"
  value       = var.enable_alb ? "https://${aws_lb.main[0].dns_name}" : null
}

# ─────────────────────────────────────────────
# Redis
# ─────────────────────────────────────────────

output "redis_endpoint" {
  description = "ElastiCache Redis configuration endpoint"
  value       = var.redis_num_cache_nodes > 0 && length(aws_elasticache_replication_group.redis) > 0 ? aws_elasticache_replication_group.redis[0].configuration_endpoint_address : null
}
