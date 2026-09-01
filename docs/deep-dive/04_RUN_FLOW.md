# 04 · Run / Trial Flow (end-to-end lifecycle)

> PayFlow; code still says "Verdict" in places (see `00_INDEX.md`).

## Trigger
- **Corpus pick:** `api.createRun(fileName)` → `POST /runs {invoice_file}` → `{run_id, invoice_file}`; the id is stashed in `main._pending`. The invoice list comes from `GET /invoices` (labels merged from `manifest.json`).
- **Upload:** `api.uploadRun(file)` → `POST /runs/upload` (multipart `FormData`, a **raw `fetch`** not `tryFetch` — `tryFetch` forces `application/json` and would break the multipart boundary — with a 20 s `AbortController`). Backend `upload_run` sanitizes the name (`safe = Path(file.filename).name`, 400 if empty), writes `data/uploads/<safe>`, returns `{run_id, invoice_file: safe}`.
- **Synchronous variant:** `POST /runs?wait=1` (or `wait:true` body) runs `orchestrator.process()` inline and returns the full `RunRecord` — used by curl/tests/`seed-demo`.

## resolve_pdf
`orchestrator.resolve_pdf(invoice_file)` accepts a bare corpus name, an upload name, or an absolute path.
It checks, in order: the path if absolute-and-exists, then `data/invoices/<name>`, `data/uploads/<name>`,
and the repo root. Raises `FileNotFoundError` if none exist (surfaced as HTTP 404 by `create_run`).

## Extraction (see `05_EXTRACTION.md` for depth)
`extraction.extract(pdf_path)`: `sha = sha256(bytes)` → `cache_read(sha)` (a hit is re-validated and returned)
→ else `get_provider().extract()` → `validate()` → `cache_write` (only if `EXTRACTION_CACHE=1`, append-only).
**Cached corpus vs live upload:** a corpus PDF has a pinned fixture → deterministic instant replay in any
provider mode. A freshly uploaded PDF has a **novel sha256 → cache miss →** a real Gemini call (needs a key /
`EXTRACTION_PROVIDER=gemini`), then it caches so a re-run in the same session is instant.

## _gather_masters (incl. multi-GR summing)
```python
vendors = store.list_vendors()
po  = store.get_po(extract.po_number) if extract.po_number else None
gr  = None
if po:
    grs = store.goods_receipts_for(po.po_number)        # ALL receipts for the PO
    if grs:
        total = round(sum(g.received_total for g in grs), 2)
        label = grs[0].gr_id if len(grs)==1 else f"{len(grs)} receipts"
        gr = GoodsReceipt(gr_id=label, po_number=po.po_number,
                          received_total=total, received_date=max(g.received_date for g in grs))
historical = [h for v in vendors for h in store.historical_invoices_for(v.vendor_id)]
```
So the engine sees **one aggregated receipt** (summed total, latest date) — a split delivery matches a single invoice.

## The 6 stages (`orchestrator._STAGE_ORDER`)
The key move: `engine.decide()` is called **exactly once** (right after `EXTRACTED`, at the `CODED` step) and
its single `DecisionResult` is **decomposed** across the later stages for display — no logic is re-run per stage.

| # | Stage | What happens | `_stage_output` payload |
|---|-------|--------------|--------------------------|
| 1 | `RECEIVED` | filename recorded | `{file}` |
| 2 | `EXTRACTED` | `extraction.extract()` runs (in `stream()`) | `{vendor_name, invoice_number, po_number, currency, total, doc_type, confidence: _overall}` |
| 3 | `CODED` | first post-extraction step → **`decide()` runs here once**; GL coding surfaced | `{account, cost_center, confidence}` |
| 4 | `MATCHED` | PO match view | `{matched_po, cumulative_after}` |
| 5 | `VALIDATED` | non-INFO flags | `{flags: [{code, severity, message}]}` |
| 6 | `DECIDED` | final verdict | `{decision, routed_to, materiality_band, reasons[], notifications[]}` |

`process()` (sync) builds all 6 `StageResult`s with `duration_ms=0`. `stream()` (async) emits per-stage events
with a `STAGE_DELAY_MS` (default **350 ms**) sleep between started/completed, measuring real `duration_ms`.

## SSE event shapes
`GET /runs/{id}/stream` returns `EventSourceResponse`; each frame is `{"data": <SSEEvent JSON>}`. The
`SSEEvent` fields: `type, run_id, stage, status, payload, ts`. Sequence per run:
```
{"type":"stage_started",   "run_id":"run_ab12…","stage":"RECEIVED", "status":"running","payload":{},        "ts":"…"}
{"type":"stage_completed", "run_id":"run_ab12…","stage":"RECEIVED", "status":"ok",     "payload":{"file":"14_multi_gr.pdf"},"ts":"…"}
…  (EXTRACTED, CODED, MATCHED, VALIDATED, DECIDED — each started then completed) …
{"type":"stage_completed", "run_id":"run_ab12…","stage":"DECIDED",  "status":"ok",     "payload":{decision,routed_to,materiality_band,reasons,notifications},"ts":"…"}
{"type":"run_completed",   "run_id":"run_ab12…","stage":"DECIDED",  "status":"APPROVE","payload":{"decision":"APPROVE"},"ts":"…"}
```
On an exception mid-stream, a `stage_completed` with `status:"fail"` and `payload.error` is emitted, then the
error re-raises. `stream_run` drains the `_pending` entry in a **`try/finally`** so it can't leak.

## Persistence
`_persist(run, result)` → `store.save_run(run)` (upserts `runs` with a denormalized `decision`, and **replaces**
`run_stages` wholesale so re-saving is idempotent) + `store.save_notification(n, run_id)` per notification.
Tables: `runs`, `run_stages`, `notifications` (+ the four master tables). Masters auto-load on startup if empty.

## The UI
- **Live Run** (`pages/LiveRun.tsx`): opens `EventSource` on `/runs/{id}/stream` via `api.streamRun`; maps `stage_started`→running, `stage_completed`→done/failed/skipped onto the **Stepper**; on `run_completed` fetches `GET /runs/{id}` to fill extracted fields + `VerdictCard`. Corpus preview via `invoiceUrl` (`GET /invoices/{name}`); an uploaded file previews via a client-side **object URL** (revoked on unmount/new-pick). If the backend is down in `auto` mode, `api.ts` replays a mock cadence.
- **Decision Flow** (`pages/DecisionFlow.tsx`): same run/stream, but on completion it calls `deriveNodes(result)` and reveals the gate ledger **node-by-node** (`revealIdx` advances every `460/speed` ms; **Replay** resets `revealIdx=0`; a **speed** control scales it). A node shows `pending` (not yet revealed) → `active` (currently revealing) → its final `state`.

## `lib/flowModel.deriveNodes(result)` — mapping a result to the trace
Pure function → an ordered `FlowNodeVM[]` (9 headline nodes; the verdict is rendered separately by the page).

**The 9 nodes** (`NODES`, in order): `intake` (Intake/Document), `vendor`, `coding` (GL Coding), `confidence`
(Confidence & Arithmetic), `po` (PO & Currency), `dup` (Duplicates), `match` (Matching & Tolerance), `bypass`
(PO-Bypass / No-PO), `anomaly` (Anomaly & Split). Each `NodeDef` has the `ReasonCode`s it owns + a `skip(ctx)`.

**Context inference** (from the result, no backend hints):
```
earlyReject = has(REJECT_NOT_INVOICE) || has(REJECT_MISSING_CRITICAL)
hasPO       = !!result.matched_po
creditMemo  = has(HOLD_CREDIT_MEMO)
```

**Per node:**
- **Owned reasons** = result reasons whose `code` the node lists. `OK_MATCH` is shared by `vendor` and `match`, so it's **disambiguated by rule text**: `vendor` claims OK_MATCH whose `rule` matches `/vendor/i`; `match` claims OK_MATCH whose `rule` matches `/tolerance|match/i`.
- **State:** `skipped` if `skip(ctx)`; else `reject` if it owns a REJECT-severity reason; else `hold` if it owns a HOLD; else `pass`.
- **Skip inference:** everything after intake skips on `earlyReject`; `po` also skips when `!hasPO`; `match` also skips on `creditMemo || !hasPO`; `bypass` skips when `hasPO` (it's the no-PO path) or `creditMemo`; `anomaly` skips on `creditMemo`. So a no-PO bypass invoice shows `po` + `match` skipped and `bypass` active; a credit memo shows the whole financial cluster skipped.
- **Chips:** the `coding` node prepends `account / cost ctr / conf%` from `gl_coding`; every node then flattens its reasons' scalar `values` into `{k, v}` chips (objects/nulls dropped), capped at 6.
- **Driving-gate detection:** `driving = state !== "skipped" && owns a non-INFO reason whose severity rank == the decision's rank`. So on a HOLD, the HOLD-severity gate(s) light as "driving"; on a REJECT, the REJECT gate(s). **On an APPROVE (rank = INFO) no gate is flagged driving** — there's no non-INFO reason at the decision's rank — which is expected (an approve has no single culprit).
