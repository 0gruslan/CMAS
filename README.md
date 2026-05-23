## 👥 Команда проекта
- Оганисян Артак
- Кривощеков Дмитрий
- Гунба Руслан

## 🧱 Общая архитектура
```
[Клиент] (Web/Моб. приложение)
    │
    ▼
[API Gateway] (FastAPI — единая точка входа)
    │
    ├── ► Микросервис 1: Пользователи и роли
    ├── ► Микросервис 2: Комнаты и проживание
    └── ► Микросервис 3: Заявки и обслуживание
```
Протокол: REST/gRPC  
База данных: отдельная БД на микросервис (PostgreSQL)  
Аутентификация: JWT (сквозной токен через Gateway)

---

## 🧩 1. Микросервис «Пользователи и роли» (Auth & Users)

Ответственность:
- Регистрация, вход, JWT-токены
- Роли: студент, комендант, администратор
- Профили пользователей (ФИО, группа, контакты)
- Привязка к комнате (только хранение ID комнаты, без логики размещения)

Модели:
- User (id, ФИО, email, пароль, роль, id_комнаты)
- Role (студент/комендант/админ)

API:
- POST /register, /login
- GET /users, /users/{id}
- PUT /users/{id}/room — назначить комнату (вызывается из другого сервиса)

---

## 🧩 2. Микросервис «Комнаты и проживание» (Rooms & Accommodation)

Ответственность:
- Этажи, комнаты, места
- Статус комнаты (свободна, частично занята, ремонт)
- Поселение/выселение
- История проживания

Модели:
- Floor (номер, общежитие)
- Room (номер, этаж, вместимость, свободно_мест)
- Residence (id_студента, id_комнаты, дата_заезда, дата_выезда)

API:
- GET /rooms, /rooms/{id}
- POST /rooms/assign — заселить
- POST /rooms/evict — выселить
- GET /floors/{id}/stats — загрузка этажа

---

## 🧩 3. Микросервис «Заявки и обслуживание» (Requests & Maintenance)

Ответственность:
- Заявки от студентов (сломалась мебель, нет воды и т.п.)
- Назначение ответственного (комендант, техслужба)
- Статусы: создана, в работе, выполнена
- Уведомления

Модели:
- Request (id, id_студента, id_комнаты, категория, описание, статус, дата)
- Comment (к заявке)

API:
- GET /requests, /requests/{id}
- POST /requests — создать заявку
- PUT /requests/{id}/status — изменить статус
- GET /requests/room/{room_id} — заявки по комнате

---

## 🌉 API Gateway (общий вход)

Задачи:
- Маршрутизация запросов к микросервисам
- Проверка JWT (кроме `/login`, `/register`, `/health`, `/`)
- Агрегация данных (например: профиль студента + его комната + его заявки)

Основные эндпоинты Gateway:
- `POST /register`, `POST /login`
- `GET /users`, `GET /users/{id}`, `PUT /users/{id}/room`
- `POST /floors`, `GET /rooms`, `POST /rooms`, `GET /rooms/{id}`
- `POST /rooms/assign`, `POST /rooms/evict`, `GET /floors/{id}/stats`
- `GET /requests`, `GET /requests/{id}`, `POST /requests`
- `PUT /requests/{id}/status`, `GET /requests/room/{room_id}`
- `POST /requests/{id}/comments`
- `GET /profile/{id}` — агрегирует данные из users + rooms + requests

Пример использования:
```bash
# 1) Логин
curl -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@cmas.local","password":"admin123"}'

# 2) Использование токена
curl http://localhost:8000/users \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## 📦 Взаимодействие между сервисами

1. Заселение студента:
   - Gateway → `POST /rooms/assign` (Rooms Service)
   - Gateway → `PUT /users/{id}/room` (Users Service, синхронизация room_id)
   - (синхронно через HTTP/gRPC или асинхронно через RabbitMQ/Kafka)

2. Создание заявки:
   - Gateway → Сервис 3 (создать заявку)
   - Сервис 3 (опционально) → Уведомление коменданту

3. Просмотр профиля:
   - Gateway → `GET /users/{id}`
   - Gateway → `GET /rooms/{room_id}` (если комната назначена)
   - Gateway → `GET /requests?student_id={id}`

---

## 🗄️ Базы данных

- Сервис 1: своя БД — users, roles
- Сервис 2: своя БД — rooms, floors, residence_history
- Сервис 3: своя БД — requests, comments

> Никаких прямых связей между БД, только через API сервисов.

---

## 🔐 Безопасность и роли

- Студент: видит только себя, свою комнату, свои заявки.
- Комендант: видит этаж/общежитие, управляет заселением, обрабатывает заявки.
- Админ: полный доступ, управление пользователями и ролями.

---

## 🚀 Запуск и миграции

Теперь сервисы работают только через PostgreSQL, без in-memory моков.

Запуск через Docker Compose:

```bash
docker compose up --build
```

Миграции Alembic для каждого сервиса применяются автоматически при старте контейнеров:
- `users_service`: `alembic upgrade head`
- `rooms_service`: `alembic upgrade head`
- `requests_service`: `alembic upgrade head`

При необходимости можно запустить вручную:

```bash
docker compose exec users_service alembic upgrade head
docker compose exec rooms_service alembic upgrade head
docker compose exec requests_service alembic upgrade head
```

---

## 📊 Мониторинг (Prometheus + Grafana + Loki)

После `docker compose up --build` доступны:

| Сервис | URL | Назначение |
|--------|-----|------------|
| **Grafana** | http://localhost:3003 | Дашборд «CMAS — метрики и логи» |
| **Prometheus** | http://localhost:9090 | Сбор метрик `/metrics` |
| **Loki** | http://localhost:3100 | Хранилище логов |

Логин Grafana по умолчанию: `admin` / `admin` (переменные `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD` в `.env`).

### Метрики

Все FastAPI-сервисы отдают Prometheus-метрики (`prometheus-fastapi-instrumentator`): RPS, latency, статусы HTTP, in-progress.

### Логи и correlation_id

Каждый запрос получает заголовок **`X-Correlation-ID`** (клиент может передать свой; иначе генерируется UUID).  
Логи в stdout — **JSON** с полями `correlation_id`, `service`, `method`, `path`, `status_code`.  
Gateway пробрасывает тот же ID в микросервисы при проксировании.

На дашборде Grafana:
- фильтр **service** — gateway / users / rooms / requests;
- поле **correlation_id** — regex (вставьте UUID из ответа API, чтобы увидеть цепочку запросов).

Пример:

```bash
curl -i http://localhost:8000/health
# смотрите заголовок X-Correlation-ID в ответе
```
