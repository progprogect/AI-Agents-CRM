# Terraform — AWS Infrastructure for Doctor Agent

Deploys the Doctor Agent application on AWS using a **unified Docker container**
(nginx + FastAPI + Next.js) — the same architecture as Railway, for consistency.

## Architecture

```
Internet → ALB (HTTPS) → ECS Fargate (unified container, port 80)
                              └── nginx (port 80)
                                    ├── /api/* /ws/*  → FastAPI (8000, internal)
                                    └── /             → Next.js  (3000, internal)

ECS → RDS PostgreSQL (private subnet, port 5432)
ECS → ElastiCache Redis (optional, private subnet)
ECS → Secrets Manager (DATABASE_URL, encryption keys, API keys)
ECS → ECR (pulls unified Docker image)
```

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **Terraform >= 1.0** installed
3. **Terraform state backend** pre-created (see below)
4. **ECR image pushed** — build and push the root `Dockerfile` before the first deploy

### State backend (one-time setup)

Terraform state is stored in S3 with DynamoDB locking. Create these manually before running `terraform init`:

```bash
# Create S3 bucket (use your own unique name)
aws s3api create-bucket \
  --bucket doctor-agent-terraform-state \
  --region <your-region> \
  --create-bucket-configuration LocationConstraint=<your-region>

aws s3api put-bucket-versioning \
  --bucket doctor-agent-terraform-state \
  --versioning-configuration Status=Enabled

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name terraform-state-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region <your-region>
```

Then update `backend.tf` with your bucket name and region.

> **Note:** The DynamoDB table in `backend.tf` is only for Terraform state locking,
> not for application data. The application uses PostgreSQL (RDS).

## Quick start

### 1. Configure variables

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your VPC, subnet IDs, passwords, etc.
```

Required variables with no defaults:
- `vpc_id` — your VPC ID
- `private_subnet_ids` — at least 2 private subnets (for RDS, ECS)
- `db_password` — RDS master password
- `secret_encryption_key` — Fernet key for encrypting channel tokens
- `jwt_secret_key` — JWT signing secret for admin panel

### 2. Push Docker image to ECR

```bash
# Get ECR login
aws ecr get-login-password --region <region> | \
  docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com

# Build and push from project root (uses the unified Dockerfile)
docker build --platform linux/amd64 -t doctor-agent-app:latest .
docker tag doctor-agent-app:latest <ecr-repo-url>:latest
docker push <ecr-repo-url>:latest
```

After `terraform apply`, use the `ecr_repository_url` output as `<ecr-repo-url>`.

### 3. Deploy

```bash
terraform init
terraform plan    # review changes
terraform apply
```

### 4. Set secrets that require manual input

Terraform creates the Secrets Manager secrets but some need values set manually
(particularly `openai-api-key` and `instagram-webhook-verify-token`):

```bash
# Set OpenAI API key
aws secretsmanager put-secret-value \
  --secret-id doctor-agent/openai-api-key \
  --secret-string "sk-..."

# Set Instagram webhook verify token
aws secretsmanager put-secret-value \
  --secret-id doctor-agent/instagram-webhook-verify-token \
  --secret-string "your-verify-token"
```

### 5. Run database migrations

After the ECS task starts, run migrations once against the new RDS instance:

```bash
# Connect to RDS (from a bastion host or via AWS Systems Manager Session Manager)
# Use the DATABASE_URL from Secrets Manager

# Run Alembic migrations (or your migration tool)
DATABASE_URL="postgresql://..." alembic upgrade head
```

## Cost overview

| Resource | Configuration | Est. monthly cost |
|---|---|---|
| ECS Fargate | 0.5 vCPU / 1 GB (1 task) | ~$15-20 |
| RDS PostgreSQL | db.t3.micro, 20 GB gp3 | ~$15-20 |
| ALB | 1 load balancer | ~$16 |
| ECR | Minimal storage | ~$1-2 |
| Secrets Manager | 5 secrets | ~$2-3 |
| ElastiCache Redis | cache.t3.micro (optional) | ~$15 |
| **Total (without Redis)** | | **~$50-60/month** |

MVP with `enable_alb = false` and `redis_num_cache_nodes = 0`:
- ECS + RDS only: **~$30-40/month**
- ⚠️ Without ALB, `assign_public_ip = true` is used (less secure)

## Outputs

After `terraform apply`, key outputs:

| Output | Description |
|---|---|
| `ecr_repository_url` | Push your unified Docker image here |
| `rds_endpoint` | RDS hostname (for manual DB access) |
| `alb_dns_name` | Point your domain's CNAME here |
| `secret_database_url_arn` | ARN of DATABASE_URL in Secrets Manager |

## Updating the application

```bash
# Rebuild and push new image
docker build --platform linux/amd64 -t doctor-agent-app:latest .
docker push <ecr-repo-url>:latest

# Force new ECS deployment
aws ecs update-service \
  --cluster doctor-agent-cluster \
  --service doctor-agent-backend \
  --force-new-deployment \
  --region <region>
```

## Destroying infrastructure

```bash
# ⚠️ This deletes RDS (db_deletion_protection must be false first)
terraform destroy
```

To disable deletion protection before destroy:
```bash
terraform apply -var="db_deletion_protection=false"
terraform destroy
```
