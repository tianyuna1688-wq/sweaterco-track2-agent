# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
RUN corepack enable && corepack prepare pnpm@11.25.0 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AUDIT_DB_PATH=/app/backend/runtime/audit.sqlite3
WORKDIR /app
COPY backend/requirements-lock.txt /tmp/requirements-lock.txt
RUN pip install --no-cache-dir -r /tmp/requirements-lock.txt && useradd --uid 10001 --create-home app
COPY backend/ /app/backend/
COPY data/ /app/data/
COPY harness/ /app/harness/
COPY evals/ /app/evals/
COPY docs/source/manifest.json /app/docs/source/manifest.json
COPY --from=frontend /build/dist/ /app/frontend/dist/
RUN mkdir -p /app/backend/runtime && chown -R app:app /app/backend/runtime /app/evals
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health')); assert d['status']=='ok'"
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
