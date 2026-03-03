# Habit Tracker Telegram Bot (MVP)

Production-ready MVP Telegram bot for habit tracking.

## Stack

- Python 3.12
- aiogram v3 (async)
- PostgreSQL + SQLAlchemy 2.0 async + Alembic
- APScheduler AsyncIOScheduler
- Timezones via `zoneinfo` (IANA timezone names)
- Config via `.env` + `python-dotenv`

## Features

- `/start` app-like home with 3 horizontal buttons:
  - `📚 Привычки`
  - `📊 Статистика`
  - `⚙️ Настройки`
- `Привычки` section:
  - `📋 Список привычек`
  - `➕ Добавить привычку`
- `Статистика` section:
  - `📅 Месяц`
  - `✅ День`
- `Настройки` section:
  - `🕒 Таймзона`
  - `🔔 Уведомления` (настройка snooze: 10/15/30/60/120 минут)
- Timezone setup (`/timezone`) from curated list:
  - `Asia/Tashkent`
  - `Europe/Moscow`
  - `Europe/Istanbul`
  - `Asia/Dubai`
  - `Asia/Almaty`
  - `Europe/London`
- Multiple habits per user
- Multiple reminder times per habit (`HH:MM`, local timezone)
- Habit management:
  - add reminder time
  - remove reminder time
  - activate/deactivate habit
- Reminder message with actions:
  - `✅ Done`
  - `⏭ Skip`
  - `📝 Snooze 10m`
- Daily summary at `23:59:59` local time
- Per-user per-local-date per-habit logs: `done/skip/not_done`
- Month analytics in text format (`✅/⚠️/❌`)
- Stable APScheduler job IDs:
  - `reminder:{user_id}:{habit_time_id}`
  - `summary:{user_id}`

## App-like UX navigation

- Bot uses one persistent "screen message" per user and edits it for navigation.
- UI state is persisted in Postgres table `ui_state`:
  - `screen_message_id`
  - `current_screen`
  - `stack` (back history)
  - `payload` (screen context, e.g. `habit_id`)
- Every screen has inline buttons and bottom navigation bar:
  - `⬅️ Back` (when history exists)
  - `🏠 Home`
- Reminder notifications are separate messages, but include:
  - `✅ Done`
  - `⏭ Skip`
  - `📝 Snooze 10m`
  - `🏠 Open app`
- Callback data is standardized and dispatched via a single callback registry.

## Security

- No secrets are hardcoded in code.
- `.env` is ignored by git.
- Use `.env.example` as template.

## Quick start

### 1) Create virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Create `.env` from template

```bash
cp .env.example .env
```

Fill values:

- `BOT_TOKEN`
- `DATABASE_URL`

### 3) Run PostgreSQL

```bash
docker compose up -d
```

### 4) Apply migrations

```bash
alembic upgrade head
```

### 5) Run the bot

```bash
python -m src.bot
```

## Health check

Check imports and database connectivity without starting polling:

```bash
python -m src.bot --check
```

## Project structure

```text
src/
  bot.py
  config.py
  db/
    base.py
    session.py
    models.py
    migrations/
  services/
    scheduler.py
    habits.py
    logs.py
    timezone.py
  handlers/
    callbacks.py
    start.py
    habits.py
  keyboards/
    habits.py
  ui/
    navigation.py
    renderer.py
```
