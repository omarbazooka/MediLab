# Single production-minded Dockerfile for MediLab AI Web Application
FROM python:3.12-slim

# Prevent Python from writing bytecode and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

# Install uv binary from official distribution
COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /bin/uv

# Create non-root system user and group for application security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Ensure non-root ownership of workdir
RUN chown appuser:appuser /app

# Copy dependency definition files first to optimize Docker layer caching
COPY pyproject.toml uv.lock ./

# Install project dependencies without project root package
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source code
COPY . .

# Complete virtual environment setup with project files
RUN uv sync --frozen --no-dev && chown -R appuser:appuser /app

# Activate virtualenv inside container PATH
ENV PATH="/app/.venv/bin:$PATH"

# Switch to non-root user
USER appuser

# Expose default Flask service port
EXPOSE 5000

# Container healthcheck probe using standard library
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health')" || exit 1

# Start the application
CMD ["python", "run.py"]
