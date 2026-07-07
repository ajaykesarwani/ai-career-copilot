# ── Stage 1: build the React frontend ──────────────────────────────────────────
FROM node:24-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# → produces /build/frontend/dist

# ── Stage 2: backend runtime (serves the API + the built frontend) ────────────
FROM python:3.11-slim
WORKDIR /app

# curl: used by the docker-compose healthcheck below.
# libgomp1: required by PyMuPDF (fitz) for scanned-PDF OCR page rendering.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/

# Built frontend lands one level up from backend/, mirroring the local
# (non-Docker) repo layout that main.py already expects via
# `Path(__file__).parent / ".." / "frontend" / "dist"`.
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

WORKDIR /app/backend
EXPOSE 8000

# Cloud Run and Render both inject a PORT env var and expect the process to
# listen on it; 8000 is the fallback for local `docker run` / docker-compose.
# `exec` replaces the shell so uvicorn (not sh) is PID 1 and receives
# SIGTERM directly for a clean shutdown.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
