# Multi-stage: the builder installs into a venv that the runtime copies, so the
# final image carries no compilers or build caches.
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

# --- runtime ---------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 riftlab

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=riftlab:riftlab alembic.ini ./
COPY --chown=riftlab:riftlab alembic ./alembic
COPY --chown=riftlab:riftlab app ./app
COPY --chown=riftlab:riftlab scripts ./scripts

RUN mkdir -p /app/models && chown -R riftlab:riftlab /app/models
USER riftlab

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
