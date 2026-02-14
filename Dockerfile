# syntax=docker/dockerfile:1

FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @openai/codex@latest \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY market_reporter/ ./market_reporter/
RUN pip install --upgrade pip && pip install .

COPY config/ ./config/
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

RUN mkdir -p /app/data /app/output

EXPOSE 8000

CMD ["market-reporter", "serve", "--host", "0.0.0.0", "--port", "8000"]
