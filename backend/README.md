# Task Control Backend (MVP)

This is the backend vertical slice of the task control center. It currently implements:

- local PostgreSQL schema and Alembic initial migration
- local account login with Argon2id, server-side sessions and CSRF
- task definitions with immutable versions and JSON Schema parameter validation
- immediate runs, local script executor, worker claim/completion, automatic retry wait
- interval/cron/once schedules, scheduler loop, pause/resume/cancel
- manual retry with parent run lineage
- execution targets and encrypted credentials
- local/SSH/HTTP executors
- run/attempt statistics API
- users, sessions, API tokens and audit event API
- retention cleanup job and security headers/rate limiting
- initial React console served from `frontend/dist` when built
- Docker Compose / Dockerfile / GitHub Actions CI
- pytest unit + integration tests

Schedules, SSH/HTTP executors, retry scheduling, statistics and the React console are still
pending tasks from `specs/001-task-control-center/tasks.md`.

## Setup

```sh
cd backend
uv sync --python 3.12 --group dev
createdb task_control
```

Create `backend/.env` from `.env.example` and set a real 32-byte base64 key. For local development:

```sh
TASK_CONTROL_DATABASE_URL=postgresql+psycopg://localhost:5432/task_control
TASK_CONTROL_SCRIPT_ROOT=/tmp/task-control-scripts
```

Generate a key:

```sh
python -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

## Migrate and bootstrap

```sh
uv run alembic upgrade head
uv run python -m task_control.cli create-admin --username admin
```

## Run

```sh
uv run uvicorn task_control.main:app --reload --port 8000
uv run python -m task_control.worker.loop
uv run python -m task_control.scheduler.loop
```

Build the console with `cd ../frontend && pnpm install && pnpm build`; FastAPI serves it at `/`.

- API docs: http://localhost:8000/api/docs
- Health: http://localhost:8000/api/v1/health/live

## Test

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The tests use the `task_control_test` database and create/drop tables per test.

## Docker

```sh
cd ..
docker compose -f deploy/docker-compose.yml up --build
```

Set a real `TASK_CONTROL_SECRET_KEYS` value before using the compose file.
