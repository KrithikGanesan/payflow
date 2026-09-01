# ---- build the React frontend (same-origin: VITE_API_BASE="") ----
FROM node:20-alpine AS fe
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- FastAPI runtime that serves API + the built SPA ----
FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY data/ data/
COPY --from=fe /fe/dist frontend/dist
ENV EXTRACTION_PROVIDER=gemini EXTRACTION_CACHE=1 DB_PATH=/tmp/verdict.db SEED_DEMO_ON_START=1
EXPOSE 8000
WORKDIR /app/backend
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
