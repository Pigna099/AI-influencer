FROM node:22-bookworm-slim AS web-build
WORKDIR /build/webui
COPY webui/package.json webui/package-lock.json ./
RUN npm ci
COPY webui/ ./
RUN npm run lint && npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
COPY --from=web-build /build/webui_dist ./webui_dist
RUN useradd --uid 1000 --create-home app && mkdir -p /app/data/media && chown -R app:app /app
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
