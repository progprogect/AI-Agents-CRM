# ─────────────────────────────────────────────
# Networking / Security Groups
# ─────────────────────────────────────────────

output "ecs_service_sg_id" {
  description = "Security Group ID for ECS tasks (unified container)"
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
  description = "RDS PostgreSQL hostname (without port)"
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
# ─────────────────────────────────────────────

output "secret_database_url_arn" {
  description = "ARN of the DATABASE_URL secret (full PostgreSQL connection string)"
  value       = aws_secretsmanager_secret.database_url.arn
}

output "secret_encryption_key_arn" {
  description = "ARN of the SECRET_ENCRYPTION_KEY secret (Fernet key)"
  value       = aws_secretsmanager_secret.secret_encryption_key.arn
}

output "secret_jwt_key_arn" {
  description = "ARN of the JWT_SECRET_KEY secret"
  value       = aws_secretsmanager_secret.jwt_secret_key.arn
}

output "openai_secret_arn" {
  description = "ARN of the OpenAI API key secret"
  value       = aws_secretsmanager_secret.openai.arn
}

output "instagram_webhook_verify_token_secret_arn" {
  description = "ARN of the Instagram webhook verify token secret"
  value       = aws_secretsmanager_secret.instagram_webhook_verify_token.arn
}

# ─────────────────────────────────────────────
# ECS / ECR — unified container
# ─────────────────────────────────────────────

output "ecr_repository_url" {
  description = "ECR repository URL — push the unified Docker image (root Dockerfile) here"
  value       = aws_ecr_repository.backend.repository_url
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
  description = "ECS service name (unified backend+frontend container)"
  value       = aws_ecs_service.backend.name
}

# ─────────────────────────────────────────────
# IAM
# ─────────────────────────────────────────────

output "iam_ecs_execution_role_arn" {
  description = "IAM role ARN for ECS task execution (pulls image, writes logs, fetches secrets)"
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
  description = "ALB DNS name — create a CNAME record pointing your domain here"
  value       = var.enable_alb ? aws_lb.main[0].dns_name : null
}

output "alb_arn" {
  description = "ALB ARN"
  value       = var.enable_alb ? aws_lb.main[0].arn : null
}

output "app_url_via_alb" {
  description = "Application URL via ALB (set your domain CNAME to alb_dns_name)"
  value       = var.enable_alb ? "https://${aws_lb.main[0].dns_name}" : null
}

# ─────────────────────────────────────────────
# Redis
# ─────────────────────────────────────────────

output "redis_endpoint" {
  description = "ElastiCache Redis configuration endpoint (null if Redis is disabled)"
  value       = var.redis_num_cache_nodes > 0 && length(aws_elasticache_replication_group.redis) > 0 ? aws_elasticache_replication_group.redis[0].configuration_endpoint_address : null
}
