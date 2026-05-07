FROM python:3.11-slim

WORKDIR /app

# Install system deps needed by lxml / pandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libxml2-dev libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY api/ ./api/
COPY data/ ./data/
COPY risk/ ./risk/
COPY monitoring/ ./monitoring/
COPY config/ ./config/
COPY strategies/ ./strategies/
COPY agents/ ./agents/

ENV PYTHONPATH=/app
ENV PORT=8000

EXPOSE 8000

CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT}
