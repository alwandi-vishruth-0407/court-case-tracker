FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY sql/ ./sql/
COPY scripts/bootstrap_cloud.py ./scripts/bootstrap_cloud.py
COPY --from=frontend /build/dist ./frontend/dist
RUN useradd --create-home appuser
USER appuser
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "python scripts/bootstrap_cloud.py && exec uvicorn main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
