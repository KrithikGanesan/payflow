# PayFlow — Invoice-to-Decision
PS-1 Finance/AP case study. Invoice PDF in → APPROVE/HOLD/REJECT with a full reasoning trail.
See `docs/superpowers/specs/2026-08-30-verdict-design.md`.

## Run
1. `backend/.env` → set `GEMINI_API_KEY` (free key from aistudio.google.com/app/apikey)
2. `./.venv/bin/pip install -r backend/requirements.txt`
3. `cd frontend && npm install`
4. `./demo`  → backend :8000, frontend :5173

Providers: `EXTRACTION_PROVIDER=gemini|ollama|fixture`. `fixture` runs with no key.
