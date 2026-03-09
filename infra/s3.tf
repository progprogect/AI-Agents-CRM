# ============================================================
# S3 Media Bucket — for STORAGE_BACKEND=s3 (AWS deployments)
# ============================================================
# Created only when enable_s3 = true (default: false).
#
# After creation:
#   1. Set STORAGE_BACKEND=s3 in ECS environment (see ecs.tf)
#   2. Set S3_BUCKET_NAME to the bucket name output
#   3. Optionally set S3_PUBLIC_URL_PREFIX to a CloudFront domain
#
# Files are served publicly (required for WhatsApp/Twilio media delivery).
# A bucket policy grants public GetObject for all objects.
# ECS task role receives PutObject and DeleteObject via iam.tf.
# ============================================================

variable "enable_s3" {
  description = "Create an S3 bucket for file storage (STORAGE_BACKEND=s3). Set to true for AWS deployments."
  type        = bool
  default     = false
}

variable "s3_media_bucket_name" {
  description = "Name of the S3 bucket for RAG documents and chat media. Must be globally unique."
  type        = string
  default     = "doctor-agent-media"
}

# ─────────────────────────────────────────────
# S3 Bucket
# ─────────────────────────────────────────────

resource "aws_s3_bucket" "media" {
  count  = var.enable_s3 ? 1 : 0
  bucket = var.s3_media_bucket_name

  tags = merge(local.common_tags, { Name = var.s3_media_bucket_name })
}

# Enable versioning for accidental-deletion protection
resource "aws_s3_bucket_versioning" "media" {
  count  = var.enable_s3 ? 1 : 0
  bucket = aws_s3_bucket.media[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption at rest
resource "aws_s3_bucket_server_side_encryption_configuration" "media" {
  count  = var.enable_s3 ? 1 : 0
  bucket = aws_s3_bucket.media[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Allow public read so files can be served directly (required for Twilio/WhatsApp media)
# If you add CloudFront later, you can restrict this to CloudFront OAC instead.
resource "aws_s3_bucket_public_access_block" "media" {
  count  = var.enable_s3 ? 1 : 0
  bucket = aws_s3_bucket.media[0].id

  block_public_acls       = true   # ACLs disabled — use bucket policy instead
  block_public_policy     = false  # Allow the public-read bucket policy below
  ignore_public_acls      = true
  restrict_public_buckets = false
}

# Public-read bucket policy: anyone can GET objects, only ECS can PUT/DELETE
resource "aws_s3_bucket_policy" "media_public_read" {
  count  = var.enable_s3 ? 1 : 0
  bucket = aws_s3_bucket.media[0].id

  # Ensure public-access block is applied first (otherwise Terraform will fail)
  depends_on = [aws_s3_bucket_public_access_block.media]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.media[0].arn}/*"
      }
    ]
  })
}

# CORS: allow browsers to load images/videos directly from S3
resource "aws_s3_bucket_cors_configuration" "media" {
  count  = var.enable_s3 ? 1 : 0
  bucket = aws_s3_bucket.media[0].id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 86400
  }
}

# ─────────────────────────────────────────────
# IAM — grant ECS task role access to the bucket
# ─────────────────────────────────────────────

resource "aws_iam_role_policy" "ecs_task_s3" {
  count = var.enable_s3 ? 1 : 0
  name  = "doctor-agent-ecs-task-s3-policy"
  role  = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:DeleteObject",
        ]
        Resource = "${aws_s3_bucket.media[0].arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.media[0].arn
      }
    ]
  })
}

# ─────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────

output "s3_media_bucket_name" {
  description = "S3 bucket name for file storage. Set S3_BUCKET_NAME=<this value> in ECS env vars."
  value       = var.enable_s3 ? aws_s3_bucket.media[0].bucket : null
}

output "s3_media_bucket_arn" {
  description = "S3 media bucket ARN"
  value       = var.enable_s3 ? aws_s3_bucket.media[0].arn : null
}

output "s3_media_bucket_domain" {
  description = "Direct S3 HTTPS URL prefix. Use as S3_PUBLIC_URL_PREFIX if not using CloudFront."
  value       = var.enable_s3 ? "https://${aws_s3_bucket.media[0].bucket}.s3.${var.aws_region}.amazonaws.com" : null
}
