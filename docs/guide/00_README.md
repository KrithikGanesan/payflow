# PayFlow — Guide (start here)

> **Naming note:** the product is being renamed **Verdict → PayFlow**. This guide uses **PayFlow**
> throughout, but the **code still says "Verdict"** in several places (sidebar brand, FastAPI title,
> `README.md`, `index.html`, DB file `verdict.db`, the repo folder `~/payflow/`) until the
> rename lands. Wherever you see "Verdict" in source, read "PayFlow".

## What is this?
PayFlow is an **accounts-payable invoice-to-decision system**: a vendor invoice PDF goes in, and a clear
**APPROVE / HOLD / REJECT** verdict comes out — with a full, plain-English reasoning trail that cites the
exact policy and values behind every gate. It is built for *judgment + explainability*: it hands an AP
clerk a pre-investigated exception with evidence, not a black-box answer. Stack: **FastAPI + SQLite +
Google Gemini** extraction (with a key-free fixture fallback) on the backend; **React + Vite + TypeScript +
Tailwind** on the frontend, with a live **SSE** stage stream.

## This guide
| File | What it covers |
|------|----------------|
| `00_README.md` | This index — what it is, how to run, build status |
| `01_WHAT_WE_BUILT.md` | Plain-English tour of every layer, the repo map, and the 5 UI screens |
| `02_HOW_IT_WORKS.md` | End-to-end data flow: extraction → 6 stages → decision gates → precedence → API → SSE → UI, with the exact thresholds |
| `03_EDGE_CASES.md` | The happy path + all 13 corpus cases: rule, threshold, decision, reason code, engine function, covering test (the primary fact-check table) |
| `04_FACT_CHECK.md` | Exact commands to verify every claim, claim→proof map, and honest caveats |

## How to run
Prereqs (per `README.md`, `PROJECT_STATE.md`): Python 3.13 venv at `~/payflow/.venv`, and
`npm install` done in `frontend/`.

```bash
# 1. (optional) put a free Gemini key in backend/.env  → aistudio.google.com/app/apikey
# 2. install deps
~/payflow/.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm install
# 3. boot backend :8000 + frontend :5173
./demo
```
`./demo` loads `backend/.env`, starts `uvicorn app.main:app --port 8000`, and `npm run dev`
(source: `demo`). Provider is chosen by `EXTRACTION_PROVIDER=gemini|ollama|fixture`; **`fixture` runs the
whole app with no key** by replaying ground-truth JSON in `data/fixtures/`.

### Verify the logic (no key needed)
```bash
# all 13 corpus invoices through the real pipeline vs the ground-truth manifest
EXTRACTION_PROVIDER=fixture ./.venv/bin/python scripts/smoke_test.py
# the 70 pure decision-engine unit tests
./.venv/bin/python -m pytest backend/tests -q
```
(sources: `scripts/smoke_test.py`, `backend/tests/`). See `04_FACT_CHECK.md` for what each output proves.

## Build status — what's done vs planned
**Done and verified (fixture mode):**
- Shared contracts (`backend/app/contracts.py` + mirror `frontend/src/contracts.ts`).
- Extraction layer: gemini / fixture / ollama providers, sha256 content-cache, arithmetic+format validation (`backend/app/extraction/`).
- Pure decision engine, 8 gate modules + precedence (`backend/app/engine/`), **70 pytest tests green**.
- SQLite store + masters loader (`backend/app/store.py`), pipeline orchestrator with 6 stages + SSE (`backend/app/orchestrator.py`), FastAPI routes (`backend/app/main.py`).
- 13 corpus invoice PDFs + ground-truth fixtures + `manifest.json`; 11 vendors / 12 POs / 4 goods receipts / 17 historical invoices.
- Frontend: 6 nav screens (incl. the **Decision Flow** gate-by-gate trace) + a run-detail view, talks to the backend via the `/api` proxy with a mock fallback.
- **Browser upload of a fresh PDF** — the Live Run and Decision Flow drop-zones capture a File and run it live through Gemini (`frontend/src/api.ts:uploadRun` → `POST /runs/upload`, traversal-guarded).

**Planned / not yet built:**
- **Verdict → PayFlow rename** (the on-screen strings and titles listed above).

_(The real-time run-trace idea has since shipped as the **Decision Flow** screen; browser upload is now wired.
Both are described below and in `01_/02_`.)_

_This guide documents what is built in the code today. The existing `docs/knowledge/*.md` are living handoff
notes; where they drift from the code, `04_FACT_CHECK.md` calls it out._
