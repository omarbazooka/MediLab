# MediLab AI

**Domain:** Diagnostic Laboratory AI Sales & Customer Service Agent  
**Current scope:** Phase 0 — Project Foundation

MediLab AI is a Flask-based assessment project that will later provide test/package discovery,
RAG-backed laboratory information, persistent conversational context, and real booking actions.
Phase 0 intentionally contains only the application/infrastructure foundation.

## Phase 0 scope

Implemented in this phase:

- Flask application factory and centralized blueprint registration
- Environment-driven configuration with strict production validation
- Flask-SQLAlchemy and Flask-Migrate extension wiring
- Structured JSON application logging with bounded request correlation IDs
- Controlled HTTP error responses with safe 500 handling
- `GET /health` process/database readiness probe
- PostgreSQL + pgvector infrastructure through Docker Compose
- One custom web `Dockerfile`
- `uv` dependency management and lockfile
- Pytest unit/integration structure and Ruff quality gates
- GitHub Actions QA for unit checks plus real Docker/PostgreSQL/pgvector runtime validation

Not implemented yet: business models, migrations/schema, seed data, LangGraph, RAG, bookings,
customer chat, or the admin dashboard. Those belong to later phases.

## Architecture

Phase 0 keeps a modular Flask monolith and avoids speculative layers.

```text
medilab-ai/
├── app/
│   ├── __init__.py              # application factory / wiring
│   ├── config.py                # environment resolution + validation
│   ├── errors.py                # centralized HTTP error handling
│   ├── extensions.py            # Flask extension singletons
│   ├── logging.py               # structured JSON logging
│   ├── request_ids.py           # bounded request-correlation middleware
│   └── blueprints/
│       ├── __init__.py          # centralized blueprint registry
│       └── health/
│           ├── __init__.py
│           └── routes.py        # operational /health endpoint
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/             # real PostgreSQL tests are marked `postgres`
├── scripts/
│   └── init-pgvector.sql
├── .github/workflows/ci.yml
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── uv.lock
├── .env.example
└── run.py
```

Blueprints remain the Flask HTTP organization mechanism. Future template surfaces (`public`, `chat`,
`admin`) and any JSON/API endpoints can be added as real requirements arrive; Phase 0 does not create
empty API modules merely for appearance.

## Requirements

- Python 3.11+ (3.12 is used in Docker/CI)
- `uv`
- Docker + Docker Compose for PostgreSQL/pgvector runtime validation

## Local setup

```bash
git clone https://github.com/omarbazooka/MediLab.git
cd MediLab
cp .env.example .env
uv sync
```

The application environment is selected with `MEDILAB_ENV`:

- `development`
- `testing`
- `production`

`FLASK_ENV` is intentionally not used.

## Run locally

Start PostgreSQL/pgvector first if the application should report healthy database readiness:

```bash
docker compose up -d db
uv run python run.py
```

Then:

```bash
curl http://127.0.0.1:5000/health
```

A healthy response is HTTP 200:

```json
{
  "status": "ok",
  "database": "connected",
  "timestamp": "..."
}
```

If the database cannot be reached, `/health` returns HTTP 503 with a controlled payload and does not
expose the connection string or traceback.

## Docker Compose

The Compose stack contains only the Phase 0 services:

- `web` — built from the single project `Dockerfile`
- `db` — `pgvector/pgvector:0.8.6-pg16-bookworm`

```bash
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs -f web
```

Stop the stack with:

```bash
docker compose down
```

To remove the assessment database volume intentionally:

```bash
docker compose down -v
```

The source tree is mounted to `/app` for development. The container virtual environment is stored at
`/opt/venv`, so the bind mount cannot hide or replace Linux dependencies with a host `.venv`.

The Phase 0 image runs `run.py` for the local/demo environment. A dedicated production WSGI command
should be selected when an actual deployment target is chosen; deployment-provider details are not
part of the current assessment phase.

## Environment variables

| Variable | Purpose | Development default |
|---|---|---|
| `MEDILAB_ENV` | application environment | `development` |
| `SECRET_KEY` | Flask signing/session secret | insecure local placeholder |
| `DATABASE_URL` | application PostgreSQL URL | local `medilab` database |
| `HOST` | local Flask bind host | `0.0.0.0` |
| `PORT` | application/host port | `5000` |
| `LOG_LEVEL` | structured log level | `INFO` |
| `POSTGRES_DB` | Compose database | `medilab` |
| `POSTGRES_USER` | Compose database user | `postgres` |
| `POSTGRES_PASSWORD` | Compose database password | local-only placeholder |
| `POSTGRES_PORT` | host PostgreSQL port | `5432` |
| `TEST_DATABASE_URL` | real PostgreSQL integration-test URL | unset |

Production configuration rejects known/default secret values, requires at least a 32-character secret,
and requires a parseable PostgreSQL URL with a database name.

## Tests and quality gates

Fast unit suite (no Docker/PostgreSQL required):

```bash
uv run pytest tests/unit
uv run ruff check .
uv run ruff format --check .
```

Real PostgreSQL/pgvector integration tests require `TEST_DATABASE_URL`:

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/medilab \
  uv run pytest -m postgres
```

On Windows PowerShell:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/medilab"
uv run pytest -m postgres
```

GitHub Actions runs both quality checks and a real Compose runtime flow: build/start containers, call
`/health`, query the installed pgvector extension, run marked PostgreSQL tests, and tear the stack down.

## Error and request handling

HTTP errors return a consistent JSON envelope:

```json
{
  "error": {
    "code": "not_found",
    "message": "The requested resource was not found."
  }
}
```

Unexpected exceptions are logged server-side and returned to clients as a generic 500 response.
Request correlation uses `X-Request-ID`; safe bounded IDs are preserved and invalid/oversized values are
replaced with a generated UUID.

## pgvector bootstrap vs migrations

`scripts/init-pgvector.sql` enables the extension when a fresh Compose PostgreSQL volume is initialized.
It is Phase 0 infrastructure bootstrap only. Starting in Phase 1, Alembic migrations become the
authoritative reproducible schema path, including extension/schema changes.

## Phase status semantics

Code existence alone is not considered completion:

- `IMPLEMENTED` — code exists
- `TESTED` — automated evidence passes
- `LIVE_VERIFIED` — real runtime evidence proves the behavior

Phase 0 should only be marked fully `LIVE_VERIFIED` after the Docker/PostgreSQL/pgvector runtime gate
passes on the current commit.

## Next phase

Phase 1 introduces SQLAlchemy business models, Alembic migrations, PostgreSQL constraints/indexes, and
realistic seed data. RAG and LangGraph remain later phases.
