# Single custom image for the MediLab AI Flask web application.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Keep uv pinned for reproducible image builds.
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /bin/uv

RUN groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /app --shell /usr/sbin/nologin appuser

WORKDIR /app

# Resolve dependencies before copying source so normal source edits reuse this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser run.py ./run.py

# There is no installable project package yet; this verifies the locked runtime env.
RUN uv sync --frozen --no-dev

USER appuser
EXPOSE 5000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3)" || exit 1

# Phase 0/demo entrypoint. A production WSGI server can replace this command at deploy time.
CMD ["python", "run.py"]
