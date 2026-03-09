# ============================================================
# RDS PostgreSQL — primary datastore for AWS deployment
# ============================================================
# The application uses DATABASE_BACKEND=postgres, which means:
#   - All data (agents, conversations, messages, RAG documents, etc.)
#     is stored in PostgreSQL tables.
#   - Channel/notification tokens are Fernet-encrypted using
#     SECRET_ENCRYPTION_KEY and stored in the `secrets` table.
#   - No DynamoDB or OpenSearch is required.
#   - RAG vector search uses cosine similarity computed in Python
#     (asyncpg + in-process). pgvector is optional for future use.
# ============================================================

# ─────────────────────────────────────────────
# Security Group
# ─────────────────────────────────────────────

resource "aws_security_group" "rds" {
  name        = "doctor-agent-rds-sg"
  description = "Allow PostgreSQL access from ECS tasks only"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from ECS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_service.id]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "doctor-agent-rds-sg" })
}

# ─────────────────────────────────────────────
# Subnet Group (RDS must be in private subnets)
# ─────────────────────────────────────────────

resource "aws_db_subnet_group" "main" {
  name        = "doctor-agent-db-subnet-group"
  description = "Private subnets for RDS PostgreSQL"
  subnet_ids  = var.private_subnet_ids

  tags = merge(local.common_tags, { Name = "doctor-agent-db-subnet-group" })
}

# ─────────────────────────────────────────────
# Parameter Group
# ─────────────────────────────────────────────

resource "aws_db_parameter_group" "postgres" {
  name        = "doctor-agent-postgres16"
  family      = "postgres16"
  description = "PostgreSQL 16 parameters for doctor-agent"

  # Log queries slower than 1 second to CloudWatch for performance analysis
  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  # Useful for debugging connection issues
  parameter {
    name  = "log_connections"
    value = "1"
  }

  tags = local.common_tags
}

# ─────────────────────────────────────────────
# RDS Instance
# ─────────────────────────────────────────────

resource "aws_db_instance" "main" {
  identifier = "doctor-agent-postgres"

  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  # Storage
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = 100      # Auto-scale up to 100 GB
  storage_type          = "gp3"
  storage_encrypted     = true     # Encryption at rest, no extra cost on gp3

  # Credentials
  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  # Networking
  db_subnet_group_name   = aws_db_subnet_group.main.name
  parameter_group_name   = aws_db_parameter_group.postgres.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false   # Only accessible from within VPC

  # High availability
  multi_az = var.db_multi_az

  # Backups
  backup_retention_period = 7              # 7-day point-in-time recovery
  backup_window           = "03:00-04:00"  # UTC, during low-traffic hours
  maintenance_window      = "Mon:04:00-Mon:05:00"
  copy_tags_to_snapshot   = true

  # Protection
  deletion_protection       = var.db_deletion_protection
  skip_final_snapshot       = false
  final_snapshot_identifier = "doctor-agent-final-snapshot"

  # Performance Insights (free tier covers 7 days)
  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  tags = merge(local.common_tags, { Name = "doctor-agent-postgres" })
}

# ─────────────────────────────────────────────
# Secrets Manager — application secrets
# ─────────────────────────────────────────────

# Full PostgreSQL connection string — injected as DATABASE_URL into ECS
resource "aws_secretsmanager_secret" "database_url" {
  name        = "doctor-agent/database-url"
  description = "Full PostgreSQL connection string for the Doctor Agent application"
  tags        = local.common_tags
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id = aws_secretsmanager_secret.database_url.id
  # Constructed automatically from RDS instance details.
  # The endpoint includes port (host:5432), so we split it and use address directly.
  secret_string = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.main.address}:5432/${var.db_name}"

  depends_on = [aws_db_instance.main]
}

# Fernet key for encrypting channel/notification tokens in Postgres
resource "aws_secretsmanager_secret" "secret_encryption_key" {
  name        = "doctor-agent/secret-encryption-key"
  description = "Fernet encryption key for channel tokens stored in PostgreSQL"
  tags        = local.common_tags
}

resource "aws_secretsmanager_secret_version" "secret_encryption_key" {
  secret_id     = aws_secretsmanager_secret.secret_encryption_key.id
  secret_string = var.secret_encryption_key
}

# JWT secret for admin panel authentication
resource "aws_secretsmanager_secret" "jwt_secret_key" {
  name        = "doctor-agent/jwt-secret-key"
  description = "JWT signing secret for admin panel sessions"
  tags        = local.common_tags
}

resource "aws_secretsmanager_secret_version" "jwt_secret_key" {
  secret_id     = aws_secretsmanager_secret.jwt_secret_key.id
  secret_string = var.jwt_secret_key
}
