variable "vpc_id" {
  description = "VPC ID where resources are located"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "me-central-1"
}

variable "project_tag" {
  description = "Project tag for all resources"
  type        = string
  default     = "doctor-agent"
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for ECS tasks and RDS"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs for ALB (required only if enable_alb = true)"
  type        = list(string)
  default     = []
}

# ─────────────────────────────────────────────
# ECS
# ─────────────────────────────────────────────

variable "ecs_cpu" {
  description = "CPU units for ECS backend task (1024 = 1 vCPU)"
  type        = number
  default     = 512
}

variable "ecs_memory" {
  description = "Memory for ECS backend task (MB)"
  type        = number
  default     = 1024
}

variable "ecs_desired_count" {
  description = "Desired number of ECS backend tasks"
  type        = number
  default     = 1
}

variable "ecr_repository_name" {
  description = "ECR repository name for the backend Docker image"
  type        = string
  default     = "doctor-agent-backend"
}

# ─────────────────────────────────────────────
# RDS — PostgreSQL
# ─────────────────────────────────────────────

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "agent_db"
}

variable "db_username" {
  description = "PostgreSQL master username"
  type        = string
  default     = "agent_admin"
}

variable "db_password" {
  description = "PostgreSQL master password. Use a strong random password and store it in your CI secrets or terraform.tfvars (gitignored)."
  type        = string
  sensitive   = true
}

variable "db_allocated_storage" {
  description = "Initial allocated storage for RDS (GB). gp3 auto-scales beyond this."
  type        = number
  default     = 20
}

variable "db_multi_az" {
  description = "Enable Multi-AZ standby for RDS (recommended for production, adds cost)"
  type        = bool
  default     = false
}

variable "db_deletion_protection" {
  description = "Prevent accidental RDS deletion. Set to false only when decommissioning."
  type        = bool
  default     = true
}

# ─────────────────────────────────────────────
# Application secrets
# ─────────────────────────────────────────────

variable "secret_encryption_key" {
  description = <<-EOT
    Fernet key used to encrypt channel/notification tokens stored in PostgreSQL.
    Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    Store this value securely — losing it makes all stored tokens unreadable.
  EOT
  type        = string
  sensitive   = true
}

variable "jwt_secret_key" {
  description = "Secret key for signing JWT admin session tokens. Use a random 32+ character string."
  type        = string
  sensitive   = true
}

variable "app_url" {
  description = "Public base URL of the deployed app (no trailing slash). Used to build webhook URLs, e.g. https://your-domain.com"
  type        = string
  default     = ""
}

# ─────────────────────────────────────────────
# ALB / HTTPS
# ─────────────────────────────────────────────

variable "enable_alb" {
  description = "Enable Application Load Balancer. Set to false for cost-saving MVP deployments."
  type        = bool
  default     = false
}

variable "certificate_arn" {
  description = "ACM certificate ARN for the HTTPS listener. Required when enable_alb = true. Request via AWS Certificate Manager or import a Let's Encrypt cert."
  type        = string
  default     = ""
}

# ─────────────────────────────────────────────
# Redis (ElastiCache)
# ─────────────────────────────────────────────

variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_num_cache_nodes" {
  description = "Number of Redis cache nodes (0 to disable ElastiCache)"
  type        = number
  default     = 1
}

# ─────────────────────────────────────────────
# Locals
# ─────────────────────────────────────────────

locals {
  common_tags = {
    Project = var.project_tag
  }
}
