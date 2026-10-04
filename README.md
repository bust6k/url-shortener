## URL-shortener
классически простой генератор коротких ссылок. Реализован в 1 файле т.к не планирует масштабироваться. Не имеет web-интерфейса, только прямые запросы через curl  

### Стек

- **FastAPI** — HTTP-слой, валидация через Pydantic v2, Swagger из коробки
- **SQLAlchemy 2.0 async** — ORM
- **Postgres 16** — хранение ссылок и кликов
- **asyncpg** — асинхронный драйвер
- **shortuuid** — генерация кодов без похожих символов (`0/O`, `1/l/I`)
- **uvicorn** — ASGI-сервер

### Возможности

- Создание короткой ссылки с проверкой уникальности кода
- Редирект по короткому коду (302)
- Сбор статистики: количество переходов, user-agent, IP, время клика
- Валидация входного URL
- Healthcheck

### Запуск

**1. Postgres в контейнере:**

```bash
docker-compose up
```

**2. Виртуальное окружение**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
**3. Конфиг**

```bash
cp .env.example .env
```
**4. Запуск**

```bash
python app.py
```
Сервер поднимется на http://localhost:8000. Схема БД создаётся автоматически при старте через Base.metadata.create_all.


## Документация

Swagger UI: **http://localhost:8000/docs**

ReDoc: **http://localhost:8000/redoc**

## API
POST /shorten

Создать короткую ссылку.

```bash
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/astral-sh/ruff"}'
```

GET /{code}

Редирект на исходный URL.
```bash

curl -i http://localhost:8000/k7m2p9x
```
GET /stats/{code}

Статистика по коду: всего переходов и последние 10 кликов.

```bash
curl -s http://localhost:8000/stats/k7m2p9x | python -m json.tool
```

GET /health

Проверяет состояние системы
```bash

curl -s http://localhost:8000/health
{"ok":true}
```

## Ограничения

Проект сознательно сделан одностраничным и минимальным. В продакшене я бы добавил:

   -  Alembic вместо create_all — для управляемых миграций

   -  Rate limit на /shorten — чтобы не заливали мусором

   -  Индексы под конкретные запросы по мере роста нагрузки

   - Кэш популярных кодов (Redis) — чтобы не бить в БД на каждом редиректе

   - Валидацию на приватные сети / loopback, чтобы не получить SSRF

   - Логирование кликов через очередь, а не синхронно в транзакции запроса

   - Тесты через pytest + httpx.AsyncClient
