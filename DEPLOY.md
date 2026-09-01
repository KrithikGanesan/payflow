# Deploying PayFlow live (Render, single URL)

The whole app runs as **one web service**: FastAPI serves the API **and** the built React SPA
from the same origin. No separate frontend host, no CORS, no proxy.

## What's already wired for production
- `Dockerfile` builds the frontend (`VITE_API_BASE=""` → calls the API at the same origin) and runs uvicorn serving both.
- `render.yaml` declares the service, env vars, and a 1 GB persistent disk at `/data` (keeps SQLite + run history across restarts).
- Mock data is **disabled in production builds** — if the API is ever unreachable the UI shows honest empty/error states, never fabricated runs.
- `SEED_DEMO_ON_START=1` auto-runs the 15 sample invoices on first boot (from cached fixtures — no API key needed) so the Dashboard/History aren't empty.

## Steps

### 1. Push to YOUR personal GitHub
```bash
cd ~/payflow
git add -A
git commit -m "PayFlow — deployable build"
# create an EMPTY repo on your personal github (github.com/new), then:
git remote add origin https://github.com/<your-personal-username>/payflow.git
git branch -M main
git push -u origin main
```
`backend/.env` (your Gemini key), `*.db`, `node_modules`, `dist`, `.venv` are all gitignored — **the key is NOT pushed.**

### 2. Create the Render service
- Render dashboard → **New → Blueprint** → connect your GitHub → pick the `payflow` repo.
- Render reads `render.yaml` and sets up the Docker web service + the `/data` disk automatically.
- When prompted, set the secret **`GEMINI_API_KEY`** = your key (it's marked `sync:false`, so Render asks).
- Click **Apply / Deploy**.

### 3. First boot
- Docker build runs (`npm ci && npm run build`, then pip install). ~3–5 min.
- On start: masters auto-seed, and the 15 sample runs auto-seed (dashboard populated).
- You get a URL like `https://payflow-xxxx.onrender.com`.

### 4. Verify + hand over
- Open the URL → the app loads (served by FastAPI).
- Upload a PDF from your Desktop set → **live Gemini** extraction runs.
- Run a sample from the dropdown → instant (cached).
- Send the interviewer the URL.

## Interview-day notes
- **Free tier sleeps** (~30–60s cold start). For the interview window, either bump to the **Starter** plan (always-on, `plan: starter` is already in `render.yaml`) or open the URL a minute before to wake it.
- Live uploads use your Gemini free-tier quota — do a warm-up upload before the call.
- To reset the demo data: redeploy, or `curl -X POST https://<url>/seed-demo`.

## Alternatives (same Dockerfile works)
- **Railway:** New Project → Deploy from repo → it detects the Dockerfile → add the same env vars + a volume at `/data`.
- **Fly.io:** `fly launch` (uses the Dockerfile) → `fly volumes create data` → mount at `/data` → set secrets with `fly secrets set GEMINI_API_KEY=...`.
