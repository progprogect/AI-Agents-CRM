# Скрипты миграции

## Миграция данных из OpenSearch в DynamoDB

### Требования

Скрипт `migrate_opensearch_to_dynamodb.py` требует дополнительных зависимостей:

```bash
pip install opensearch-py boto3
```

### Использование

1. Установите переменные окружения:
```bash
export OPENSEARCH_ENDPOINT="https://your-opensearch-endpoint"
export OPENSEARCH_USERNAME="admin"
export OPENSEARCH_PASSWORD="your-password"
export AWS_REGION="me-central-1"
```

2. Запустите миграцию:
```bash
python migrate_opensearch_to_dynamodb.py example_agent
```

или

```bash
python migrate_opensearch_to_dynamodb.py --agent-id example_agent
```

### Примечания

- Скрипт экспортирует все документы агента из OpenSearch
- Данные импортируются в таблицу DynamoDB `doctor-agent-rag-documents`
- После успешной миграции можно удалить OpenSearch domain через Terraform
