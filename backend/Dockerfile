FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка зависимостей
# Этот слой будет кэшироваться, если requirements.txt не изменился
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
# Этот слой будет пересобираться только при изменении кода
COPY app/ ./app/

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Railway и другие платформы передают PORT через env
# Health check использует PORT для совместимости с Railway
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD sh -c 'curl -f http://localhost:${PORT:-8000}/health || exit 1'

# Порт приложения (Railway задаёт PORT динамически)
EXPOSE 8000

# Запуск: используем PORT из окружения (Railway) или 8000 по умолчанию
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]







