# CMAS — система управления общежитием

Микросервисное веб-приложение для учёта проживания, пользователей и заявок на обслуживание.

**Репозиторий:** https://github.com/0gruslan/CMAS

## 👥 Команда проекта

- Оганисян Артак
- Кривощеков Дмитрий
- Гунба Руслан

---

## 🧱 Архитектура

```
[Клиент — React :3000]
        │  /api/*
        ▼
[API Gateway — FastAPI :8000]  JWT, маршрутизация, агрегация
        │
        ├──► Users Service    :8001  →  PostgreSQL users_db    :5433
        ├──► Rooms Service    :8002  →  PostgreSQL rooms_db    :5434
        └──► Requests Service :8003  →  PostgreSQL requests_db :5435

[Prometheus :9090]  [Loki :3100]  [Grafana :3003]
```

- **Протокол:** REST (HTTP)
- **БД:** отдельная PostgreSQL на микросервис, без прямых связей между базами
- **Аутентификация:** JWT через Gateway
- **Связь сервисов:** только через API Gateway и общие ID (`student_id`, `room_id`)

---

## 🚀 Быстрый старт

### 1. Настройка окружения

```bash
cp .env.example .env
# при необходимости отредактируйте пароли и порты
```

### 2. Запуск

```bash
docker compose up --build
```

### 3. Адреса сервисов

| Сервис | URL | Описание |
|--------|-----|----------|
| **Frontend** | http://localhost:3000 | Веб-интерфейс |
| **API Gateway** | http://localhost:8000/docs | Swagger, единая точка входа |
| Users Service | http://localhost:8001/docs | Пользователи, JWT |
| Rooms Service | http://localhost:8002/docs | Комнаты, заселение |
| Requests Service | http://localhost:8003/docs | Заявки на ремонт |
| **Grafana** | http://localhost:3003 | Метрики и логи (`admin` / `admin`) |
| Prometheus | http://localhost:9090 | Сбор метрик |
| Loki | http://localhost:3100 | Хранилище логов |

Миграции Alembic применяются при старте контейнеров (`alembic upgrade head`).

---

## 🧩 Микросервисы

### 1. Пользователи и роли (Users)

- Регистрация, вход, JWT
- Роли: `student`, `commandant`, `admin`
- Профиль, поле `room_id` (синхронизируется при заселении)

**API:** `POST /register`, `POST /login`, `GET /users`, `GET /users/{id}`, `PUT /users/{id}/room`

### 2. Комнаты и проживание (Rooms)

- Этажи, комнаты, свободные места
- Статусы: `free`, `partial`, `repair`
- Заселение / выселение, история `residences`
- Статистика этажа

**API:** `POST /floors`, `POST /rooms`, `GET /rooms`, `GET /rooms/{id}`, `POST /rooms/assign`, `POST /rooms/evict`, `GET /floors/{id}/stats`

### 3. Заявки и обслуживание (Requests)

- Заявки студентов, статусы: `created` → `in_progress` → `done`
- Комментарии к заявкам

**API:** `GET /requests`, `POST /requests`, `GET /requests/{id}`, `PUT /requests/{id}/status`, `GET /requests/room/{room_id}`, `POST /requests/{id}/comments`

---

## 🌉 API Gateway

- Маршрутизация ко всем микросервисам
- Проверка JWT (кроме `/login`, `/register`, `/health`, `/`)
- **Агрегация:** `GET /profile/{id}` — user + room + requests
- **Оркестрация:** при `POST /rooms/assign` и `/rooms/evict` — Rooms, затем синхронизация Users

Пример:

```bash
# Логин
curl -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@cmas.local","password":"admin123"}'

# Запрос с токеном
curl http://localhost:8000/rooms \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## 📦 Взаимодействие между сервисами

1. **Заселение:** Gateway → `POST /rooms/assign` (Rooms) → `PUT /users/{id}/room` (Users)
2. **Выселение:** Gateway → `POST /rooms/evict` (Rooms) → `PUT /users/{id}/room` с `room_id: null`
3. **Профиль:** Gateway → Users + Rooms (если есть комната) + Requests по `student_id`
4. **Заявка:** Gateway → Requests; `student_id` и `room_id` хранятся как ID без FK в чужие БД

Микросервисы **не вызывают друг друга напрямую** — только Gateway.

---

## 📊 Мониторинг

Стек: **Prometheus** + **Grafana** + **Loki** + **Promtail**.

### Метрики

Каждый FastAPI-сервис отдаёт `/metrics` (библиотека `prometheus-fastapi-instrumentator`): RPS, latency, HTTP-статусы.

На дашборде Grafana **«CMAS — метрики и логи»**:
- нагрузка и ошибки 5xx по сервисам;
- latency p50/p95;
- графики по статусам HTTP.

### Логи и correlation_id

- Заголовок **`X-Correlation-ID`** в каждом ответе (можно передать в запросе).
- Логи в JSON: `correlation_id`, `service`, `method`, `path`, `status_code`.
- Gateway пробрасывает ID в downstream-сервисы.
- В Grafana — фильтр по `correlation_id` для просмотра цепочки запросов.

```bash
curl -i http://localhost:8000/health
# заголовок X-Correlation-ID в ответе
```

Переменные Grafana в `.env`: `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`, `GRAFANA_PORT`.

---

## 🗄️ Базы данных

| Сервис | Контейнер | Порт (хост) | Таблицы |
|--------|-----------|-------------|---------|
| Users | `users_db` | 5433 | users |
| Rooms | `rooms_db` | 5434 | floors, rooms, residences |
| Requests | `requests_db` | 5435 | maintenance_requests, request_comments |

---

## 🔐 Роли

| Роль | Доступ |
|------|--------|
| **student** | Свой профиль, своя комната, свои заявки |
| **commandant** | Заселение, заявки, комнаты этажа |
| **admin** | Полный доступ |

---

## 🧪 Тесты

```bash
pip install -r requirements.txt
python -m pytest users_service/tests/ -v
python -m pytest rooms_service/tests/ -v
python -m pytest requests_service/tests/ -v
```

Тесты используют SQLite in-memory и `TestClient` (без Docker).

CI: GitHub Actions — lint (flake8) и pytest для всех трёх микросервисов (`.github/workflows/ci-cd.yml`).

---

## 📁 Структура репозитория

```
CMAS/
├── gateway/              # API Gateway
├── users_service/
├── rooms_service/
├── requests_service/
├── frontend/             # React + Vite
├── shared/cmas_shared/   # correlation_id, JSON-логирование
├── prometheus/
├── grafana/provisioning/ # дашборды и datasources
├── loki/
├── promtail/
├── docker-compose.yml
└── requirements.txt
```

---

## 🛠 Полезные команды

```bash
# Миграции вручную
docker compose exec rooms_service alembic upgrade head

# Логи сервиса
docker compose logs -f rooms_service

# Пересборка одного сервиса
docker compose up --build rooms_service
```
