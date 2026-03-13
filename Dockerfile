# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Build stage: install dependencies into a virtual environment
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed by some packages (e.g. asyncpg compiles C ext)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy packaging metadata and source so setuptools can locate the app package
COPY pyproject.toml README.md ./
COPY app/ app/

# Create and populate the venv with runtime dependencies only (no [dev] extras)
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir .

# ---------------------------------------------------------------------------
# Runtime stage: lean image with only what is needed to run the app
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Runtime dependency of asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Bring in the pre-built venv from the builder stage (all deps + compiled exts)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source and packaging metadata
COPY app/ ./app/
COPY pyproject.toml README.md ./

# Create an editable install so all sub-packages (app.api, app.core, …) are
# importable. This only writes a .pth pointer — no recompilation occurs because
# all compiled extensions were already installed in the builder stage.
RUN pip install --no-cache-dir --no-build-isolation --no-deps -e . \
 && chown -R appuser:appuser /app

USER appuser

# Expose the default uvicorn port
EXPOSE 8000

# DATABASE_URL must be supplied at runtime (e.g. via --env or docker-compose).
# The default below points to a service named "db" as used in docker-compose.yml.
ENV DATABASE_URL="postgresql+asyncpg://postgres:postgres@db:5432/commerce_demo" \
    API_PREFIX="/api/v1" \
    AUTO_CREATE_SCHEMA="true" \
    DEFAULT_LIMIT="20" \
    MAX_LIMIT="100"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
