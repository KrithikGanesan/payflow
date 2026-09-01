# 01 · Architecture

> PayFlow; code still says "Verdict" in places (see `00_INDEX.md`).

## Component & data-flow diagram

```
                          ┌───────────────────────────────────────────────────────────┐
                          │  FRONTEND  (React + Vite + TS + Tailwind)  :5173            │
                          │                                                             │
  browser ──────────────▶│  main.tsx (router)                                          │
   pick corpus / upload   │   ├─ LiveRun.tsx        ── stepper (6 stages)               │
                          │   ├─ DecisionFlow.tsx   ── gate-by-gate reveal (flowModel)  │
                          │   ├─ Dashboard / History / ExceptionQueue / AuditTrail      │
                          │   └─ RunDetail.tsx                                          │
                          │  api.ts  (auto|mock|live; createRun / uploadRun / streamRun)│
                          └───────────────┬───────────────────────────────┬────────────┘
                            REST /api/*   │ (Vite proxy strips /api)       │  SSE  /runs/{id}/stream
                                          ▼                                ▼
        ┌──────────────────────────────────────────────────────────────────────────────┐
        │  BACKEND  FastAPI  app/main.py   :8000                                         │
        │   GET /health · GET /runs · GET /runs/{id} · POST /runs · POST /runs/upload    │
        │   GET /runs/{id}/stream (SSE) · POST /runs/{id}/decision · POST /seed-demo     │
        │   GET /invoices · GET /invoices/{name}                                         │
        └───────┬──────────────────────────────┬───────────────────────────┬────────────┘
                │                               │                           │
                ▼                               ▼                           ▼
   ┌────────────────────────┐   ┌──────────────────────────────┐   ┌───────────────────────┐
   │ orchestrator.py        │   │ extraction/  (interface.py)   │   │ store.py  (SQLite)    │
   │  resolve_pdf()         │──▶│  extract(pdf):                │   │  vendor_master        │
   │  process() / stream()  │   │   sha256 → cache_read ──hit──▶│   │  po_master            │
   │  6 stages, decide ONCE │   │   ↓ miss                      │   │  goods_receipts       │
   │  _gather_masters()     │◀──│   provider.extract()          │   │  historical_invoices  │
   │   (sums multi-GR)      │   │    ├─ gemini.py (Gemini +     │   │  runs / run_stages    │
   └───────────┬────────────┘   │    │   pdfplumber text layer) │   │  notifications        │
               │                │    └─ fixture_provider.py     │   └───────────────────────┘
               ▼                │   validate.py (arith+format)  │              ▲
   ┌────────────────────────┐   │   cache_write (append-only)   │              │ save_run /
   │ engine/  (pure)        │   └───────────────┬───────────────┘   save_notification
   │  decide.decide()       │                   │  data/fixtures/<sha256>.json
   │   ├ vendors  ├ coding  │                   ▼
   │   ├ matching ├ tolerance│          Google Gemini API (gemini-2.0-flash)
   │   ├ duplicates ├ anomaly│          (only on a cache miss w/ a real key)
   │   └ policy (+config)   │
   │  → DecisionResult      │        data/masters/*.json ── load_masters() ─▶ store (on startup if empty)
   └────────────────────────┘        data/invoices/*.pdf  (15-invoice corpus)
```

**Read path of a run:** frontend triggers `POST /runs` (or `/runs/upload`) → orchestrator `resolve_pdf` →
`extraction.extract` (cache/provider/validate) → `engine.decide` (once) → `store.save_run` → SSE events →
frontend renders stepper + verdict + (optionally) the Decision Flow trace.

## Each component's responsibility

| Component | File(s) | Responsibility |
|-----------|---------|----------------|
| **Contracts** | `backend/app/contracts.py` (+ `frontend/src/contracts.ts` mirror) | Pydantic data shapes shared by every layer: `InvoiceExtract`, `PurchaseOrder`, `Vendor`, `GoodsReceipt`, `HistoricalInvoice`, `Reason`, `DecisionResult`, `RunRecord`, `StageResult`, `SSEEvent`; enums `Stage`, `Decision`, `Severity`, `DocType`, `ReasonCode` (23 codes). No logic. |
| **API** | `backend/app/main.py` | FastAPI routes at root (Vite proxy strips `/api`). CORS for :5173. Startup: `store.init_db()` + `load_masters()` if empty. Holds `_pending: {run_id → invoice_file}` so the SSE stream knows what to process. |
| **Orchestrator** | `backend/app/orchestrator.py` | `resolve_pdf` (corpus/upload/abs path); `_gather_masters` (vendors, PO, **summed goods receipts**, history); the 6-stage pipeline; `process()` (sync) + `stream()` (async SSE). Calls `engine.decide` **once** and decomposes the result across stages. |
| **Extraction** | `backend/app/extraction/` | `interface.extract` = cache→provider→validate→cache. Providers: `gemini` (default), `fixture` (key-free), `ollama` (local). `cache.py` content-addresses by sha256(PDF). `validate.py` arithmetic + format + `_overall` confidence. |
| **Engine** | `backend/app/engine/` | Pure decision functions. `config.py` (all thresholds), one module per gate family, `decide.py` (orchestrates gates + precedence). Input = contracts objects; output = `DecisionResult`. No I/O. |
| **Store** | `backend/app/store.py` | SQLite (stdlib `sqlite3`). Master data + append-only runs/stages/notifications. Models ↔ JSON text columns. `goods_receipts_for(po)` returns ALL receipts for summing. |
| **Frontend** | `frontend/src/` | 6 nav screens + RunDetail. `api.ts` = data access with `auto|mock|live` modes and an SSE/`EventSource` client. `lib/flowModel.ts` maps a `DecisionResult` → gate nodes for the Decision Flow trace. |

## Tech choices — and why

| Choice | Why |
|--------|-----|
| **FastAPI** | Async-native (needed for the SSE stream via `sse_starlette`), Pydantic-first so `contracts.py` models are the request/response types directly, tiny surface for a single-service app. |
| **SQLite (stdlib)** | Zero-config, one file (`verdict.db`), no server to run for a demo. Masters + run history fit comfortably; models are stored as JSON text so the Pydantic model stays the source of truth for shape. |
| **SSE (not WebSockets)** | The stream is one-directional (server → browser stage events). SSE over plain HTTP is simpler, proxies cleanly through Vite, and `EventSource` auto-reconnects. Event shape in `04_RUN_FLOW.md`. |
| **Pure-function engine** | Every gate is `(contracts...) -> list[Reason]` with **no I/O**, so each is unit-testable in isolation and the whole `decide()` is deterministic. This is the defensible core — **70 tests** pin it. |
| **Provider-agnostic extraction** | `EXTRACTION_PROVIDER=gemini|ollama|fixture` chosen at runtime, imports lazy (selecting `fixture` never imports google-generativeai). Lets the same pipeline run live, local, or key-free. |
| **Fixture caching (sha256)** | Extraction is cached by the **content hash of the PDF** → deterministic replay + a key-free demo path. A slow/flaky API call can never kill a demo (re-run replays the cache), yet a *fresh* upload (novel hash) still makes a genuine live call. Append-only: a hand-authored ground-truth fixture is never clobbered. |
| **Gemini free tier** | Strong document vision + a genuinely free tier (AI Studio). Bedrock was abandoned (lost account access). Ollama kept as a no-key local fallback. |

## Repo map
```
backend/app/
  contracts.py            # shared Pydantic shapes + enums (23 ReasonCodes)
  main.py                 # FastAPI routes, CORS, startup seed, _pending map
  orchestrator.py         # resolve_pdf, _gather_masters (multi-GR sum), 6-stage process()/stream()
  store.py                # SQLite: masters + runs/stages/notifications
  engine/
    config.py             # ALL thresholds (no logic)
    decide.py             # gate order + precedence + routing + notifications
    vendors.py coding.py matching.py tolerance.py duplicates.py anomaly.py policy.py
  extraction/
    interface.py          # extract() entrypoint + provider factory
    cache.py              # sha256 content cache (append-only)
    gemini.py fixture_provider.py ollama.py
    validate.py           # arithmetic + format + _overall confidence
backend/tests/            # 70 pytest tests (pure engine)
data/
  invoices/*.pdf          # 15-invoice corpus (01…15)
  fixtures/<sha>.json     # ground-truth extract per PDF + manifest.json
  masters/*.json          # vendors(13) / purchase_orders(14) / goods_receipts(6) / historical_invoices(17)
  uploads/                # POST /runs/upload writes here (also searched by resolve_pdf)
frontend/src/
  main.tsx api.ts contracts.ts
  pages/  LiveRun DecisionFlow Dashboard History ExceptionQueue AuditTrail RunDetail
  lib/    flowModel.ts (gate nodes) useRuns notes format status cn
  components/  Stepper VerdictCard ReasonList/Dialog Timeline DocumentPreview ExtractedFields …
scripts/  seed.py  smoke_test.py  generate_corpus.py
demo      # boots backend :8000 + frontend :5173
```
