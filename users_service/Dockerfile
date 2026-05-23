FROM python:3.11-slim

WORKDIR /app

# Копирование requirements.txt из корня проекта
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/cmas_shared ./cmas_shared
COPY users_service/ .

# Открыть порт
EXPOSE 8001

# Команда запуска (переопределяется в docker-compose)
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8001"]
