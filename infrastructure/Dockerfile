FROM python:3.11-slim-bookworm AS base

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl git tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Kolkata
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Install Poetry
RUN pip install --no-cache-dir poetry==1.8.3
RUN poetry config virtualenvs.create false

# Dependencies
COPY pyproject.toml poetry.lock* ./
RUN poetry install --without dev --no-root

# Application code
COPY . .

# Create non-root user
RUN useradd -m -u 1001 iqf && chown -R iqf:iqf /app
USER iqf

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/system/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
