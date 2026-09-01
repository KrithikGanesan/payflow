# 01 · What We Built

> Product name **PayFlow**; the code still says "Verdict" in places until the rename lands (see `00_README.md`).

A plain-English tour of every layer, the repo map, and the 5 UI screens. Everything here points at a real file.

## The layers, top to bottom

| Layer | Where | What it does |
|-------|-------|--------------|
| **Shared contracts** | `backend/app/contracts.py` (+ mirror `frontend/src/contracts.ts`) | Pydantic models = the single data shape everything codes against: `InvoiceExtract`, `PurchaseOrder`, `Vendor`, `GoodsReceipt`, `HistoricalInvoice`, `Reason`, `DecisionResult`, `RunRecord`, `SSEEvent`, plus the `Stage`, `Decision`, `Severity`, `DocType`, and 22-value `ReasonCode` enums. Pure schema, no logic. |
| **Extraction** | `backend/app/extraction/` | Turns a PDF into a validated `InvoiceExtract`. Provider-agnostic (gemini/ollama/fixture), content-addressed cache, post-extraction validation. |
| **Decision engine** | `backend/app/engine/` | Pure functions. Each gate takes contracts objects and returns `list[Reason]`; `decide.py` runs them all and applies precedence. No I/O. |
| **Persistence** | `backend/app/store.py` | SQLite (stdlib `sqlite3`). Master data + append-only runs/stages/notifications. Models serialized to JSON text columns. |
| **Orchestrator** | `backend/app/orchestrator.py` | Wires extraction → engine into a 6-stage pipeline. Two entry points: `process()` (sync) and `stream()` (async SSE). |
| **API** | `backend/app/main.py` | FastAPI routes at root (`/health`, `/runs`, `/runs/{id}`, `/runs/{id}/stream`, `/runs/{id}/decision`, `/runs/upload`, `/seed-demo`, `/invoices`). |
| **Frontend** | `frontend/src/` | React + Vite + TS + Tailwind. Router in `main.tsx`; data access in `api.ts`; 6 nav screens + a run-detail page. |

> Note: the stale `PROJECT_STATE.md` repo-layout block describes a `backend/app/api/` package "not yet built" —
> there is **no** such directory; the routes live in `main.py`.

## Extraction layer (`backend/app/extraction/`)

| File | Role |
|------|------|
| `interface.py` | Public `extract(pdf_path)` entrypoint + provider factory `get_provider()`. Flow: **cache → provider → validate → cache**. Provider chosen by `EXTRACTION_PROVIDER` (default `gemini`); imports are lazy so `fixture` never imports google-generativeai. |
| `cache.py` | Content-addressed cache. Keyed by `sha256(pdf bytes)` → `data/fixtures/<sha>.json`. **Reads always allowed** (deterministic replay); **writes gated on `EXTRACTION_CACHE=1` and append-only** (never clobbers a ground-truth fixture). |
| `gemini.py` | Default provider. Sends the raw PDF bytes **and** the pdfplumber text layer to `gemini-2.0-flash`; a strict schema prompt pins the exact JSON, forces doc-type detection, and demands `null` (never guess) + a per-field confidence map. Requires `GEMINI_API_KEY` only at call time. |
| `fixture_provider.py` | Key-free deterministic provider: replays `data/fixtures/<sha>.json`. Raises a clear error if no fixture exists for a PDF. |
| `ollama.py` | Local-LLM fallback (text-layer only). Reuses the gemini prompt/parser. Errors clearly on a scanned PDF or unreachable server. |
| `validate.py` | Post-extraction checks: **(1) arithmetic** (Σ line amounts ≈ subtotal; subtotal+tax+freight−discount ≈ total) → `validation.line_items_sum_ok` / `subtotal_plus_tax_ok`; **(2) format** (ISO-4217 currency, dates parse, tax rate 0–30%) which lowers offending per-field confidence; **(3) overall confidence** folded into `confidence["_overall"]` — arithmetic failure caps it hard. Pure, idempotent. |

## Decision engine (`backend/app/engine/`)

| File | Gate(s) | Reason codes it can emit |
|------|---------|--------------------------|
| `config.py` | All tunable thresholds (no logic) | — |
| `decide.py` | Runs every gate, applies **precedence** (REJECT > HOLD > APPROVE), computes overall confidence, materiality band, DOA routing, notifications | `OK_CLEAN` (+ orchestration) |
| `vendors.py` | Approved-vendor gate, fuzzy name match (token_set_ratio blended with Jaro-Winkler), remit-to bank-change flag | `OK_MATCH`, `HOLD_VENDOR_FUZZY`, `HOLD_VENDOR_UNAPPROVED`, `HOLD_BANK_CHANGE` |
| `coding.py` | GL account + cost-centre prediction from vendor defaults | `HOLD_CODING_LOW_CONF` |
| `matching.py` | 2-way / 3-way PO match + cumulative over-billing guard | `OK_MATCH`, `HOLD_OVERBILL` |
| `tolerance.py` | Subtotal-vs-PO price tolerance (tax/freight excluded) | `OK_MATCH`, `HOLD_TOLERANCE` |
| `duplicates.py` | Exact-key duplicate (REJECT) + fuzzy resubmission (HOLD) | `REJECT_DUP_EXACT`, `HOLD_DUP_FUZZY` |
| `anomaly.py` | Spend burst vs vendor history | `HOLD_ANOMALY` |
| `policy.py` | Doc-type, missing-critical, PO status, credit memo, currency, confidence gate, PO-bypass (+finance notify), split-threshold, materiality band, DOA routing | `REJECT_NOT_INVOICE`, `REJECT_MISSING_CRITICAL`, `REJECT_PO_EXPIRED`, `REJECT_NO_PO_OVER_BYPASS`, `HOLD_CREDIT_MEMO`, `HOLD_CURRENCY`, `HOLD_LOW_CONFIDENCE`, `HOLD_MATERIALITY`, `HOLD_SPLIT_THRESHOLD`, `OK_BYPASS` |

Thresholds and the exact gate order are in `02_HOW_IT_WORKS.md`.

## Persistence (`backend/app/store.py`)
SQLite tables: `vendor_master`, `po_master`, `goods_receipts`, `historical_invoices` (masters), and
`runs`, `run_stages`, `notifications` (produced by the orchestrator). `load_masters()` loads the four
`data/masters/*.json` files (INSERT OR REPLACE, idempotent). DB path from env `DB_PATH` (default
`verdict.db`). `update_cumulative_billed()` exists for split-PO accounting but the pipeline does not call
it during a run — cumulative-after is computed read-only.

## Data (`data/`)
- `data/invoices/*.pdf` — the 13-invoice corpus (`01_clean_exact.pdf` … `13_exact_duplicate.pdf`).
- `data/fixtures/<sha>.json` — one ground-truth extract per corpus PDF (keyed by content hash) + `manifest.json` (filename → sha256, scenario, `expected_decision`, note).
- `data/masters/` — `vendors.json` (11), `purchase_orders.json` (12), `goods_receipts.json` (4), `historical_invoices.json` (17).
- `data/uploads/` — where `POST /runs/upload` writes, and where `resolve_pdf` also looks.

## Scripts
| Script | Does |
|--------|------|
| `scripts/seed.py` | Init DB schema + load masters, print row counts + vendor summary. |
| `scripts/smoke_test.py` | Run every corpus PDF through the real pipeline (fixture mode) and assert each decision matches `manifest.json`. Exits non-zero on any mismatch. |
| `scripts/generate_corpus.py` | Generates the corpus PDFs (reportlab). |

## The frontend — 6 screens + a detail view
Router: `frontend/src/main.tsx`. Nav items: `frontend/src/components/Layout.tsx` (`NAV`, 6 entries). Data
access + mock fallback + SSE: `frontend/src/api.ts`. The app runs in `auto`/`mock`/`live` mode — in `auto`
it hits the real backend and falls back to bundled mock data (`src/mock/data.ts`) if the backend is down.

| # | Screen | Route / file | What it does |
|---|--------|--------------|--------------|
| 1 | **Live Run** | `/` · `pages/LiveRun.tsx` | Pick a corpus invoice from the dropdown **or drop/choose a fresh PDF** (a hidden `<input type="file">` + drop-zone capture the `File`, preview it via an object URL, and run it live through Gemini). Watch the 6-stage **Stepper** light up over SSE; shows source PDF (left) next to extracted fields with per-field confidence (right), then the `VerdictCard`. Trigger: `uploadedFile ? uploadRun(file) : createRun(fileName)` → then `streamRun` → `GET /runs/{id}/stream`. Object URL is revoked on unmount/new-pick. |
| 2 | **Decision Flow** | `/flow` · `pages/DecisionFlow.tsx` (+ `lib/flowModel.ts`) | Real-time, gate-by-gate **decision trace**. Run a corpus invoice or upload a fresh PDF, watch the 6 stages stream, then the verdict reveals **gate by gate** — 9 headline gates (Intake, Vendor, GL Coding, Confidence & Arithmetic, PO & Currency, Duplicates, Matching & Tolerance, PO-Bypass, Anomaly & Split) + the final verdict. Each gate shows pass/hold/reject/skipped, the compared numbers, and a plain-English reason; the gate(s) that **drove** the decision are flagged. Includes **Replay** + a **speed** control. `flowModel.deriveNodes(result)` maps a `DecisionResult` onto the gates (read-only view — no engine logic duplicated). |
| 3 | **Dashboard** | `/dashboard` · `pages/Dashboard.tsx` | KPI tiles (STP rate, exception rate, avg cycle time, …), a status donut, and bar charts over all runs (Recharts). Metrics computed client-side from `useRuns()`. |
| 4 | **History** | `/history` · `pages/History.tsx` | Sortable, searchable, filterable table of every run (invoice #, vendor, amount, status, confidence, cycle time, date). Row → Run Detail. |
| 5 | **Exceptions** | `/exceptions` · `pages/ExceptionQueue.tsx` | Queue of HOLD runs not yet resolved. Keyboard-fast (j/k/a) approve/reject-with-reason via `ReasonDialog`; resolutions tracked client-side in `lib/notes.ts`. |
| 6 | **Audit Trail** | `/audit` · `pages/AuditTrail.tsx` | Chronological, "immutable" log of every run + stage, actor (AI vs human), and latest resolution. Row → Run Detail. |
| — | **Run Detail** | `/runs/:id` · `pages/RunDetail.tsx` | Drill-in for one run: `VerdictCard`, stage `Timeline`, source PDF, extracted fields, and approve/reject-with-reason. Reached from History/Exceptions/Audit and the Live Run "Open audit trail" button. |

Supporting components: `Stepper`, `VerdictCard`, `ReasonList`, `ReasonDialog`, `DocumentPreview`
(renders the PDF in an iframe via `invoiceUrl` → `GET /invoices/{name}`), `ExtractedFields`,
`ConfidenceBadge`, `StatusPill`, `KpiTile`, `Timeline`, plus `ui/Button` and `ui/Card`.
