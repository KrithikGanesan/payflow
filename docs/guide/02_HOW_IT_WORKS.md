# 02 · How It Works (end-to-end)

> Product name **PayFlow**; code still says "Verdict" in places (see `00_README.md`).

One invoice, start to finish: **select/upload → extract → 6 pipeline stages → decision gates in order →
precedence → persist → API → SSE → UI.**

## 1. Trigger a run
- **Corpus picker (wired):** the Live Run dropdown lists real invoices from `GET /invoices`
  (`main.py` reads `data/invoices/*.pdf` + labels from `manifest.json`). Selecting one and pressing
  *Process* calls `createRun(fileName)` → `POST /runs {invoice_file}` (`api.ts`, `main.py:create_run`).
- **Seed:** `POST /seed-demo` runs every corpus PDF to populate the dashboard (`main.py:seed_demo`).
- **Upload (WIRED):** the Live Run **and** Decision Flow drop-zones capture a `File` (drop-zone + a hidden
  `<input type="file">`), preview it via an object URL, and call `uploadRun(file)` (`api.ts`) → `POST /runs/upload`.
  `uploadRun` uses a raw `fetch` with a `FormData` body (not `tryFetch`, which would force `application/json` and
  break the multipart boundary) and its own `AbortController` (20 s timeout). The backend
  (`main.py:upload_run`) **sanitizes the filename** with `Path(file.filename).name` (path-traversal guard, 400 on
  empty), writes to `data/uploads/`, and returns a `run_id`. A *fresh* PDF has a novel sha256 → cache miss → real
  live Gemini call, then it's cached (append-only). Four demo PDFs live at `~/Desktop/payflow_demo/`
  (Acme $12k→APPROVE, Stark $10.3k→HOLD overbill, Cyberdyne $40k→HOLD anomaly, Umbrella $385→APPROVE+notify).

`POST /runs` without `?wait=1` returns `{run_id, invoice_file}` and stashes it in `_pending` so the SSE
stream knows what to process; with `?wait=1` (or `wait:true` body) it runs `orchestrator.process()`
synchronously and returns the full `RunRecord` (used by curl/tests).

## 2. Extraction (`extraction.extract(pdf_path)`)
Flow (`interface.py`): **`sha256(pdf)` → cache_read → (else provider) → validate → cache_write**.
1. **Cache/fixture lookup** by content hash → `data/fixtures/<sha>.json`. A hit is re-validated (idempotent) and returned — deterministic replay, and the entire path the `fixture` provider uses.
2. **Provider** (`EXTRACTION_PROVIDER`, default `gemini`): Gemini gets the PDF bytes + pdfplumber text layer + a strict schema prompt (`gemini.py`); returns fields, per-field `confidence`, `doc_type`.
3. **Validation** (`validate.py`): arithmetic → `validation["line_items_sum_ok"]` / `["subtotal_plus_tax_ok"]`; format checks lower shaky per-field confidence; overall signal stored at `confidence["_overall"]` (arithmetic failure caps it to `min(x,0.50)*0.7`).
4. **Cache write** only if `EXTRACTION_CACHE=1` and no file for that hash exists (append-only).

## 3. The 6 pipeline stages (`orchestrator.py`)
Key design: the orchestrator calls `engine.decide()` **once** (right after extraction) and **decomposes**
that single result across the stages purely for the live view — it does not re-run logic per stage.
`_STAGE_ORDER = RECEIVED, EXTRACTED, CODED, MATCHED, VALIDATED, DECIDED`. In `stream()` each stage emits
`stage_started` then (after `STAGE_DELAY_MS`, default **350 ms**) `stage_completed`, ending with `run_completed`.

| # | Stage | What runs / is surfaced | Source (`_stage_output`) |
|---|-------|-------------------------|--------------------------|
| 1 | `RECEIVED` | The filename | `{file}` |
| 2 | `EXTRACTED` | `extraction.extract()` runs here (stream) | vendor, invoice#, po#, currency, total, doc_type, `confidence._overall` |
| 3 | `CODED` | First stage after extraction → **`decide()` runs once here**; surfaces GL coding | `{account, cost_center, confidence}` |
| 4 | `MATCHED` | PO match result | `{matched_po, cumulative_after}` |
| 5 | `VALIDATED` | Non-INFO flags from the decision | `flags: [{code, severity, message}]` |
| 6 | `DECIDED` | Final verdict + routing + all reasons + notifications | `{decision, routed_to, materiality_band, reasons[], notifications[]}` |

`process()` (sync) does the same work with no delays/events. Both build a `RunRecord` (with `cycle_time_ms`,
`actor="ai"`) and call `_persist()` → `store.save_run()` + `store.save_notification()`.

## 4. The decision gates, in the order `decide()` runs them
`decide(extract, vendors, po, goods_receipt, historical_invoices)` in `engine/decide.py`:

| Order | Gate (function) | Emits | Notes |
|-------|-----------------|-------|-------|
| 0 | **Early REJECT short-circuit** — `policy.document_type` + `policy.missing_critical` | `REJECT_NOT_INVOICE`, `REJECT_MISSING_CRITICAL` | If either fires, returns REJECT immediately (skips everything below). Critical fields = vendor_name, invoice_number, invoice_date, total. |
| 1 | `vendors.check` | `OK_MATCH` / `HOLD_VENDOR_FUZZY` / `HOLD_VENDOR_UNAPPROVED` / `HOLD_BANK_CHANGE` | Also returns the matched vendor used by coding/anomaly/bypass. |
| 2 | `coding.predict` | `HOLD_CODING_LOW_CONF` | GL account+cost-centre from vendor defaults. |
| 3 | `policy.po_status` | `REJECT_PO_EXPIRED` | PO closed/expired. |
| 4 | `policy.credit_memo` | `HOLD_CREDIT_MEMO` | If set, **skips** matching/tolerance/bypass/anomaly/split below. |
| 5 | `policy.confidence_gate` | `HOLD_LOW_CONFIDENCE` | Arithmetic-fail OR any per-field confidence < 0.80. **Ignores the `_overall` meta key** (only real fields gate). |
| 6 | `policy.currency` | `HOLD_CURRENCY` | Invoice currency ≠ PO currency. |
| 7 | `duplicates.check` | `REJECT_DUP_EXACT` / `HOLD_DUP_FUZZY` | Exact-key beats fuzzy. |
| 8 | `matching.check` *(if not credit memo)* | `OK_MATCH` / `HOLD_OVERBILL` | 2-way/3-way + cumulative over-billing. |
| 9 | `tolerance.check` *(if not credit memo)* | `OK_MATCH` / `HOLD_TOLERANCE` | Subtotal vs PO; tax/freight excluded. |
| 10 | `policy.po_bypass` *(if not credit memo)* | `OK_BYPASS` / `HOLD_MATERIALITY` / `REJECT_NO_PO_OVER_BYPASS` | Only when **no PO**. Emits a `bypass_notice` notification on OK_BYPASS. |
| 11 | `anomaly.check` *(if not credit memo)* | `HOLD_ANOMALY` | Vs same-vendor history; an unmatched vendor gets an empty history (`[]`), so no false anomaly/split. |
| 12 | `policy.split_threshold` *(if not credit memo)* | `HOLD_SPLIT_THRESHOLD` | Sibling invoices dodging the approval limit. |
| — | **Precedence** `_precedence()` | — | Any `REJECT` severity → REJECT; else any `HOLD` → HOLD; else APPROVE. If pure-approve with no INFO reason, appends `OK_CLEAN`. |
| — | Routing + fraud flag | notifications | `approver_route` note for HOLD/APPROVE; `fraud_flag` note if any `HOLD_BANK_CHANGE`. |

> **Why gate order matters for reason codes:** `matching` (8) runs before `tolerance` (9), so when both fire
> the *top* (first non-INFO) reason is `HOLD_OVERBILL` — this is why corpus case 05 shows `HOLD_OVERBILL`
> rather than `HOLD_TOLERANCE`. The decision (HOLD) is identical either way. See `03`/`04`.

Overall confidence (`_overall_confidence`) = `min( min(extract.confidence.values()), gl.confidence )`,
rounded to 4 dp (note: it currently includes the `_overall` meta key in that `min`).

## 5. The exact thresholds (`backend/app/engine/config.py`)

| Control | Constant(s) | Value | Rule |
|---------|-------------|-------|------|
| Price tolerance | `TOLERANCE_PCT`, `TOLERANCE_ABS` | **±1%** and **$25** | Auto-clear only within the **tighter** of the two; beyond → `HOLD_TOLERANCE`. Under-billing never holds. |
| PO-bypass ceiling | `PO_BYPASS_LIMIT` | **$500** | No-PO + approved + bypass vendor + amount **< $500** → `OK_BYPASS`; `≥ $500` no-PO → `REJECT_NO_PO_OVER_BYPASS`; under but not bypass-eligible → `HOLD_MATERIALITY`. |
| Duplicate weights | `DUP_WEIGHT_AMOUNT/DATE/INVOICE_NO/LINE_ITEMS` | **40 / 20 / 20 / 20** | Weighted fuzzy score. |
| Duplicate sub-thresholds | `DUP_AMOUNT_PCT`, `DUP_DATE_WINDOW_DAYS`, `DUP_INVOICE_JW_THRESHOLD`, `DUP_LINE_ITEMS_THRESHOLD` | **1%, 7d, 0.90 (Jaro-Winkler), 90 (token_set_ratio)** | Conditions that add each weight. |
| Fuzzy duplicate hold | `DUP_FUZZY_HOLD_SCORE` | **≥ 70** | → `HOLD_DUP_FUZZY`. |
| Exact duplicate | `DUP_EXACT_AMOUNT_ABS`, `DUP_EXACT_DATE_WINDOW_DAYS` | **$0.01, 7d** | Same vendor + normalized invoice# + amount-to-cent + date within 7d (or unparseable) → `REJECT_DUP_EXACT`. |
| Vendor name match | `VENDOR_MATCH_AUTO`, `VENDOR_MATCH_FLOOR` | **92 / 80** | `≥92` auto-match; `80–92` → `HOLD_VENDOR_FUZZY`; `<80` → `HOLD_VENDOR_UNAPPROVED` (treated as no confident match). |
| Extraction confidence gate | `CONFIDENCE_GATE` | **0.80** | Any per-field confidence below → `HOLD_LOW_CONFIDENCE` (also if arithmetic failed). |
| GL coding gate | `CODING_CONFIDENCE_GATE` | **0.80** | Below → `HOLD_CODING_LOW_CONF`. |
| GL coding confidence tiers | `CODING_CONF_FULL/PARTIAL/NONE` | **0.95 / 0.55 / 0.20** | Both defaults present / one / neither. |
| Spend anomaly | `ANOMALY_MEAN_MULTIPLIER`, `ANOMALY_MAX_MULTIPLIER`, `ANOMALY_MIN_HISTORY` | **5× mean, 2× max, min 2 prior** | `> 5×` vendor mean OR `> 2×` vendor max → `HOLD_ANOMALY`. |
| Split-to-avoid-threshold | `SPLIT_WINDOW_DAYS`, `SPLIT_THRESHOLD` | **14d, $5,000** | ≥2 invoices each < limit within window summing ≥ limit → `HOLD_SPLIT_THRESHOLD`. |
| DOA routing bands | `DOA_MANAGER`, `DOA_DIRECTOR`, `DOA_VP` | **$5k / $25k / $100k** | `<5k` manager · `5k–25k` director · `25k–100k` VP · `>100k` CFO. Bands: `<5k / 5k-25k / 25k-100k / >100k`. |

Over-billing guard (`matching.py`): cumulative billed against a PO may not exceed `po_total × (1 + TOLERANCE_PCT)`;
3-way match additionally requires billed ≤ goods received × (1 + tolerance), and a required-but-missing GR → `HOLD_OVERBILL`.

## 6. Persistence, API, SSE, UI
- **Persist:** `save_run()` upserts the `RunRecord` (+ denormalized decision) and replaces its stages; notifications appended (`store.py`). Masters auto-load on startup if empty (`main.py:_startup`).
- **API:** `GET /health`, `GET /runs`, `GET /runs/{id}`, `POST /runs`, `POST /runs/upload`, `GET /runs/{id}/stream` (SSE via `sse_starlette`), `POST /runs/{id}/decision` (human override → sets decision, `actor="human"`, audit notification), `POST /seed-demo`, `GET /invoices`, `GET /invoices/{name}` (serves the PDF).
- **SSE:** `stream_run` looks up the pending invoice, then yields `orchestrator.stream()` events as `{data: <SSEEvent JSON>}`.
- **UI:** `api.ts` opens an `EventSource` on `/runs/{id}/stream`; `LiveRun.tsx` maps `stage_started`/`stage_completed`/`run_completed` onto the Stepper, then fetches the full run (`GET /runs/{id}`) to fill extracted fields + verdict. If the backend is unreachable in `auto` mode it replays a mock cadence.
