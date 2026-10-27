# CaseFile in one image: the React UI is built first, then copied next to the Python API, which serves it at "/".

# ---- Stage 1: build the UI (Node is only needed here, so it doesn't end up in the final image) ----
FROM node:24-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: the Python server ----
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/app/models
WORKDIR /app/backend

COPY backend/requirements.txt ./
# Long timeout and retries: one stalled download shouldn't fail the whole build on a slow connection.
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements.txt

# Download the embedding model while building, so a cold start doesn't download it again (~130 MB).
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

COPY backend/casefile ./casefile
COPY --from=frontend /frontend/dist /app/frontend/dist

# Run as a normal user, not root: if the app were ever compromised, the attacker gets fewer rights.
RUN useradd --create-home casefile && chown -R casefile /app/models
USER casefile

# Render passes the port in $PORT. 0.0.0.0 = reachable from outside the container.
# One worker: each worker loads its own embedding model, and two don't fit in 512 MB.
CMD uvicorn casefile.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
