# ════════════════════════════════════════════════════════════════════
# Stage 1: Frontend bouwen (Node.js)
# ════════════════════════════════════════════════════════════════════
FROM node:20-alpine AS frontend-builder

WORKDIR /build

# Dependencies eerst (betere layer-caching)
COPY frontend/package*.json ./
RUN npm ci

# Broncode kopiëren en productiebuild aanmaken
# VITE_API_BASE_URL="" zorgt dat API-calls relatief via /api/* lopen
COPY frontend/ ./
RUN VITE_API_BASE_URL="" npm run build

# ════════════════════════════════════════════════════════════════════
# Stage 2: Python backend (productie)
# ════════════════════════════════════════════════════════════════════
FROM python:3.11-slim

# Systeemafhankelijkheden: ffmpeg (vereist voor audio-conversie)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python-afhankelijkheden installeren (apart laag voor betere caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend broncode kopiëren
COPY backend/ ./backend/

# Gebouwde frontend uit Stage 1 kopiëren
COPY --from=frontend-builder /build/dist ./frontend/dist

# Non-root gebruiker aanmaken voor veiligheid
RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app

USER appuser

# Poort vrijgeven
EXPOSE 8000

# Healthcheck op /api/health
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Uvicorn starten
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
