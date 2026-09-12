# MediLab AI

> **Domain:** Diagnostic Laboratory AI Sales & Customer Service Agent  
> **Status:** Phase 0 — Project Foundation

---

## 1. Project Overview

**MediLab AI** is an intelligent sales and customer service agent for a diagnostic laboratory. The application will eventually assist patients and laboratory staff with diagnostic test and package discovery, branch and home-visit appointment scheduling, pre-test preparation instructions, and booking management via a conversational agent and an administrative dashboard.

### Current Implementation Status: Phase 0 Foundation

This repository currently implements **Phase 0 (Project Foundation)** only. In accordance with the project specification:
- **No business domain models** (e.g. `LabTest`, `Booking`, `Branch`) are created yet.
- **No RAG retrieval, vector search pipelines, or LangGraph orchestration workflows** are implemented yet.
- **No administrative dashboards, chat UI, or booking business logic** are implemented yet.

Phase 0 strictly establishes a clean, maintainable, production-ready foundation with:
- Modular Flask monolith layout with the application factory pattern (`create_app`)
- Environment configuration validation with strict production rules
- Centralized extensions initialization (`Flask-SQLAlchemy`, `Flask-Migrate`)
- Robust structured logging (JSON formatted with `request_id` correlation)
- Centralized HTTP error handling (400, 404, 405, 500 without leaking stack traces or internal secrets)
- Docker & Docker Compose setup using a single custom web image and PostgreSQL with pgvector (`pgvector/pgvector:pg16`)
- Automated testing suite with Pytest and Ruff linting/formatting

---

## 2. Technology Stack (Phase 0)

| Layer / Concern | Technology | Purpose |
| :--- | :--- | :--- |
| **Language** | Python 3.11+ (Python 3.12 / 3.13) | Core runtime |
| **Framework** | Flask 3.x | Application server (Application Factory & Blueprints) |
| **Database ORM** | Flask-SQLAlchemy / SQLAlchemy 2.x | Relational persistence abstraction |
| **Database Migrations** | Flask-Migrate / Alembic | Schema migration management |
| **Database & Vector Storage** | PostgreSQL + pgvector (`pgvector:pg16`) | Primary relational and vector database |
| **Package Management** | uv | Deterministic, high-speed dependency resolution |
| **Containerization** | Docker & Docker Compose | Container orchestration (`web` and `db`) |
| **Testing** | pytest, pytest-flask | Unit and integration test suite |
| **Code Quality** | Ruff | Linter and code formatter |

---

## 3. Project Structure

```text
medilab-ai/
├── app/
│   ├── __init__.py           # Flask application factory (create_app)
│   ├── config.py             # Environment configurations & validation rules
│   ├── extensions.py         # Extension singletons (SQLAlchemy, Migrate)
│   ├── logging.py            # Structured JSON logger & Request ID formatting
│   ├── errors.py             # Centralized JSON error handlers (400, 404, 405, 500)
│   └── blueprints/
│       ├── __init__.py
│       └── health/           # Health probe blueprint (/health)
│           ├── __init__.py
│           └── routes.py
├── tests/
│   ├── conftest.py           # Test fixtures (app, client, isolated sqlite)
│   ├── unit/
│   │   ├── test_config.py    # Configuration & security validation tests
│   │   ├── test_factory.py   # Application factory & request ID middleware tests
│   │   └── test_errors.py    # Error handling & traceback suppression tests
│   └── integration/
│       ├── test_health.py    # Health endpoint contracts & degradation tests
│       └── test_db.py        # Database connectivity & pgvector extension tests
├── scripts/
│   └── init-pgvector.sql     # PostgreSQL entrypoint SQL enabling pgvector
├── Dockerfile                # Single production-minded web application image
├── docker-compose.yml        # Multi-container orchestration (web + db)
├── .dockerignore             # Excluded files from Docker build context
├── pyproject.toml            # Project metadata, dependencies, and tool settings
├── uv.lock                   # Deterministic dependency lockfile
├── .env.example              # Environment variables template
├── .gitignore                # Source control ignore rules
├── run.py                    # Application launch entrypoint
└── README.md                 # Project documentation
```

---

## 4. Local Development Setup

### 4.1 Prerequisites
- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) (installed and available on PATH)
- Docker & Docker Compose (optional for local running, required for containerized deployment)

### 4.2 Installation & Dependency Synchronization

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd medilab
   ```

2. **Sync dependencies with `uv`:**
   ```bash
   uv sync
   ```
   This creates a virtual environment at `.venv` and installs all locked dependencies.

3. **Configure the environment:**
   ```bash
   cp .env.example .env
   ```
   Inspect and adjust `.env` as needed. For local development, safe default values are preconfigured.

---

## 5. Running the Application

### 5.1 Running Locally (outside Docker)

To run the Flask application locally using `uv`:
```bash
uv run python run.py
```
By default, the server listens on `http://127.0.0.1:5000`.

### 5.2 Running via Docker Compose

Docker Compose manages both the `web` application and the `db` (PostgreSQL + pgvector) services.

1. **Verify Docker Compose configuration:**
   ```bash
   docker compose config
   ```

2. **Build and start containers:**
   ```bash
   docker compose up -d --build
   ```

3. **Check container status:**
   ```bash
   docker compose ps
   ```

4. **View logs:**
   ```bash
   docker compose logs -f web
   ```

5. **Stop containers:**
   ```bash
   docker compose down
   ```

---

## 6. Health Probe Endpoint

The application provides a machine-readable health check endpoint:

```http
GET /health
```

### Healthy Response (HTTP 200 OK)
Returned when both the Flask process and database connectivity are operational:
```json
{
  "status": "ok",
  "database": "connected",
  "timestamp": "2026-09-12T18:00:00.000000+00:00"
}
```

### Degraded Response (HTTP 503 Service Unavailable)
Returned when the database probe fails, without leaking sensitive connection details, credentials, or stack traces:
```json
{
  "status": "degraded",
  "database": "disconnected",
  "timestamp": "2026-09-12T18:00:00.000000+00:00"
}
```

---

## 7. Automated Testing & Code Quality

### 7.1 Running Automated Tests
```bash
uv run pytest
```
The test suite validates:
- Flask application factory initialization and test config overrides
- Request ID generation and header preservation
- Configuration validation (rejecting insecure secrets and malformed database URIs in production)
- Error handling (verifying structured JSON output and suppressing internal server tracebacks)
- Health check contracts and database probe degradation handling
- Database connectivity and pgvector extension query support

### 7.2 Running Code Linting & Formatting
```bash
# Check code style and rules
uv run ruff check .

# Check code formatting
uv run ruff format --check .

# Auto-apply format fixes
uv run ruff format .
```

---

## 8. Environment Variables Reference

| Variable | Required in Production | Default (Dev) | Description |
| :--- | :---: | :--- | :--- |
| `FLASK_ENV` | No | `development` | Environment mode (`development`, `testing`, `production`). |
| `SECRET_KEY` | **Yes** | `dev-insecure-...` | Cryptographic secret for signing sessions. Enforces ≥16 chars in production. |
| `DATABASE_URL` | **Yes** | `postgresql+psycopg://...` | PostgreSQL connection string. Must start with `postgresql://` or `postgresql+psycopg://`. |
| `PORT` | No | `5000` | Port for the HTTP server. |
| `LOG_LEVEL` | No | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `POSTGRES_DB` | No | `medilab` | PostgreSQL database name (used by Docker Compose). |
| `POSTGRES_USER` | No | `postgres` | PostgreSQL username (used by Docker Compose). |
| `POSTGRES_PASSWORD` | No | `postgres` | PostgreSQL password (used by Docker Compose). |

---

## 9. Docker Architecture

- **Single Custom Web Dockerfile:** The application utilizes exactly ONE multi-stage/slim `Dockerfile` based on `python:3.12-slim` utilizing `uv` for reproducible, deterministic builds and runs under an unprivileged `appuser` system user.
- **PostgreSQL + pgvector:** Official `pgvector/pgvector:pg16` image is used for the database container.
- **Automated Extension Provisioning:** On first boot, `./scripts/init-pgvector.sql` executes `CREATE EXTENSION IF NOT EXISTS vector;` to ensure vector capabilities are ready for subsequent phases.
- **Persistent Volume:** Stored in named volume `postgres_data`.
- **Hot-Reloading in Development:** Mounts the host directory `.:/app` into the web container.

---

## 10. Future Roadmap & Limitations

The following components are intentionally **deferred** to subsequent phases:
- **Phase 1+ Data Models:** `LabTest`, `TestCategory`, `Package`, `Branch`, `Booking`, `Customer`, `KnowledgeDocument`, `KnowledgeChunk`.
- **Phase 1+ RAG & Search:** Vector embeddings, cosine similarity search with pgvector, PostgreSQL Full-Text Search (tsvector), and chunking pipelines.
- **Phase 1+ Agent Orchestration:** LangGraph state machine, tool-calling agents, clarification loops, and conversation persistence.
- **Phase 1+ Booking Workflows:** Branch appointment scheduling, home-visit booking logic, status inquiry, and cancellation.
- **Phase 1+ Administrative Dashboard:** Managed RAG CRUD, user authorization, and booking management UI.
