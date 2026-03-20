# Быстрый старт - Настройка AWS и Деплой

## Шаг 1: Настройка AWS Credentials

Выполните одну из команд:

### Вариант A: Интерактивная настройка (рекомендуется)

```bash
aws configure
```

Введите:
- **AWS Access Key ID**: ваш Access Key ID
- **AWS Secret Access Key**: ваш Secret Access Key
- **Default region name**: `me-central-1`
- **Default output format**: `json` (или просто Enter)

### Вариант B: Переменные окружения

```bash
export AWS_ACCESS_KEY_ID="your-access-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret-access-key"
export AWS_DEFAULT_REGION="me-central-1"
```

### Проверка настроек

```bash
aws sts get-caller-identity --region me-central-1
```

Должен вернуться Account ID: `760221990195`

## Шаг 2: Проверка/Создание секрета OpenAI

```bash
# Проверка существования
aws secretsmanager describe-secret \
  --region me-central-1 \
  --secret-id doctor-agent/openai

# Если не существует - создайте:
aws secretsmanager create-secret \
  --region me-central-1 \
  --name doctor-agent/openai \
  --description "OpenAI API key for AI Agents CRM" \
  --secret-string "sk-your-openai-api-key-here"
```

## Шаг 3: Деплой инфраструктуры

```bash
cd infra

# Автоматический деплой (рекомендуется)
./DEPLOY.sh

# Или вручную:
terraform init
terraform plan -var-file="terraform.tfvars"
terraform apply -var-file="terraform.tfvars"
```

## Что будет создано

- OpenSearch domain (~10-15 минут)
- ECS Cluster и Service
- ECR Repository
- IAM Roles
- CloudWatch Log Groups
- Secrets Manager secrets

**Время выполнения:** ~15-20 минут

**Стоимость:** ~$45-60/месяц (без ALB и Redis)

## После деплоя

1. Задайте пароль OpenSearch:
```bash
aws secretsmanager put-secret-value \
  --region me-central-1 \
  --secret-id doctor-agent/opensearch \
  --secret-string "your-secure-password"
```

2. Соберите и загрузите Docker образ (см. README.md)

3. Проверьте статус ECS service:
```bash
aws ecs describe-services \
  --cluster doctor-agent-cluster \
  --services doctor-agent-backend \
  --region me-central-1
```








