# 04 · Fact-Check Guide

> Product name **PayFlow**; the code still says "Verdict" in places until the rename lands (see `00_README.md`).

How to independently verify every claim in this guide. All commands run from the repo root
`~/payflow/`. None require a Gemini key.

## The three commands that prove the most

### 1. All 13 corpus invoices → correct decisions
```bash
EXTRACTION_PROVIDER=fixture ./.venv/bin/python scripts/smoke_test.py
```
Runs every PDF in `data/invoices/` through the **real** pipeline (extraction → engine → orchestrator) in
fixture mode and compares each decision to `data/fixtures/manifest.json`. Prints a per-file table
(`file · expected · actual · top_reason · PASS/FAIL`) and exits non-zero on any mismatch.
**Proves:** the end-to-end pipeline produces the manifest's expected APPROVE/HOLD/REJECT for all 13
(the `03_EDGE_CASES.md` "Expected" column). You'll also see case 05's `top_reason` is `HOLD_OVERBILL` and
case 08's is `HOLD_VENDOR_UNAPPROVED` — the documented caveats, live.
> Note: this writes run rows into `verdict.db` (the local SQLite file) as a side effect; it does not touch fixtures.

### 2. The 70 decision-engine unit tests
```bash
./.venv/bin/python -m pytest backend/tests -q
```
**Proves:** each gate + precedence behaves as documented. Counts: `test_policy.py` 22, `test_decide.py` 14,
`test_matching.py` 7, `test_tolerance.py` 7, `test_duplicates.py` 6, `test_vendors.py` 6, `test_coding.py` 4,
`test_anomaly.py` 4 = **70** (verify: `grep -rc "def test" backend/tests/*.py`).

### 3. Hit the live API
```bash
./demo   # in one terminal (backend :8000, frontend :5173)

# in another terminal:
curl -s localhost:8000/health | python3 -m json.tool
# → {"status":"ok","provider":"...","runs":N,"vendors":11}

# synchronous run of a corpus invoice → full RunRecord with the verdict:
curl -s -X POST 'localhost:8000/runs?wait=1' \
  -H 'Content-Type: application/json' \
  -d '{"invoice_file":"10_spend_anomaly.pdf"}' | python3 -m json.tool
# → result.decision == "HOLD", a reason with code "HOLD_ANOMALY"

# the scenario-labeled corpus the picker uses:
curl -s localhost:8000/invoices | python3 -m json.tool

# live 6-stage SSE stream (start a run without wait, then stream its id):
RID=$(curl -s -X POST localhost:8000/runs -H 'Content-Type: application/json' \
      -d '{"invoice_file":"01_clean_exact.pdf"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["run_id"])')
curl -sN "localhost:8000/runs/$RID/stream"
# → stage_started/stage_completed events for RECEIVED…DECIDED, then run_completed
```
**Proves:** routes, persistence, and the SSE stage stream (`main.py`, `orchestrator.py`) work end-to-end.

## Claim → proof map

| Claim | Verify with |
|-------|-------------|
| Thresholds are what `02` lists | `sed -n '1,60p' backend/app/engine/config.py` |
| Gate order in `decide()` | `sed -n '39,148p' backend/app/engine/decide.py` |
| Precedence REJECT>HOLD>APPROVE | `decide._precedence` + `test_decide.py::test_precedence_*` |
| 6 stages, single `decide()` call decomposed | `backend/app/orchestrator.py` (`_STAGE_ORDER`, `_stage_output`, `stream`/`process`) |
| Extraction: cache→provider→validate→cache | `backend/app/extraction/interface.py::extract` |
| Cache keyed by sha256(pdf), append-only, write gated on `EXTRACTION_CACHE=1` | `backend/app/extraction/cache.py` |
| Arithmetic failure caps confidence | `backend/app/extraction/validate.py::compute_overall_confidence` |
| Corpus counts 4/8/1 + expected decisions | `python3 -m json.tool data/fixtures/manifest.json` |
| Masters: 11 vendors / 12 POs / 4 GR / 17 hist | `for f in data/masters/*.json; do echo "$f: $(python3 -c "import json;print(len(json.load(open('$f'))))")"; done` |
| Case 05 fixture is PO-1004 / subtotal 10300 | `python3 -c "import json;d=json.load(open('data/fixtures/00722fdb52c79c3afff6806ff9f456376269ff9d1911c58d6827671c8198ef84.json'));print(d['po_number'],d['subtotal'],d['total'])"` |
| Case 08 vendor-name score < 80 floor | `./.venv/bin/python -c "from rapidfuzz.fuzz import token_set_ratio; from rapidfuzz.distance import JaroWinkler; c='acme corp'; n='acme corporation inc'; print((token_set_ratio(c,n)+JaroWinkler.similarity(c,n)*100)/2)"` → ≈75.5 |
| 6 nav screens (incl. Decision Flow) | `grep -n "to:" frontend/src/components/Layout.tsx` |
| Upload wired (multipart, abort timeout) | `grep -n "uploadRun\|FormData\|AbortController" frontend/src/api.ts` |
| Upload filename sanitized (traversal guard) | `sed -n '97,107p' backend/app/main.py` (`Path(file.filename).name`) |
| Decision Flow gate model (9 gates) | `grep -n "label:" frontend/src/lib/flowModel.ts` + `frontend/src/pages/DecisionFlow.tsx` |
| contracts.ts mirrors contracts.py | `sed -n '1,31p' frontend/src/contracts.ts` |

## Bug-hunt — 7 fixes applied (all verified)

A review pass found and fixed 7 issues. Re-verified afterward: **70 tests pass, 13/13 integration
(`smoke_test.py`), frontend build clean, path traversal blocked.**

| Sev | Fix | Where | Verify |
|-----|-----|-------|--------|
| HIGH | `confidence_gate` now ignores the `_overall` meta key (it was counted as a field, causing spurious HOLD on live uploads) | `backend/app/engine/policy.py::confidence_gate` (`not k.startswith("_")`) | `grep -n "startswith" backend/app/engine/policy.py` |
| HIGH | `/runs/upload` sanitizes the filename → path-traversal fixed | `backend/app/main.py::upload_run` (`Path(file.filename).name`) | `sed -n '97,107p' backend/app/main.py` |
| MED | SSE `_pending` entry drained in a `try/finally` (no leak if the stream errors) | `backend/app/main.py::stream_run` | `sed -n '119,127p' backend/app/main.py` |
| MED | `uploadRun` has an `AbortController` timeout (20 s) | `frontend/src/api.ts::uploadRun` | `grep -n "AbortController\|setTimeout" frontend/src/api.ts` |
| LOW | Object URL revoked on unmount / new pick (no leak) | `frontend/src/pages/LiveRun.tsx`, `DecisionFlow.tsx` | `grep -n "revokeObjectURL" frontend/src/pages/*.tsx` |
| LOW | Anomaly & split get an **empty** history (`[]`) for an unmatched vendor (no false positive) | `backend/app/engine/decide.py` (`vendor_hist = … if vendor_id else []`) | `sed -n '100,104p' backend/app/engine/decide.py` |
| LOW | Duplicate amount-weight uses `hist.amount is not None` (a legit $0 amount no longer skips the check) | `backend/app/engine/duplicates.py::_fuzzy_score` | `grep -n "is not None" backend/app/engine/duplicates.py` |

## Known caveats (be honest about these)
- **Case 05** surfaces `HOLD_OVERBILL` not `HOLD_TOLERANCE`; **case 08** surfaces `HOLD_VENDOR_UNAPPROVED` not
  `HOLD_VENDOR_FUZZY`. Both still HOLD, matching the manifest. Explained in `03_EDGE_CASES.md`.
- **Browser upload is now wired** (was planned). `frontend/src/api.ts:uploadRun` posts multipart to
  `POST /runs/upload`; the Live Run and Decision Flow drop-zones capture and preview the file and run it live.
  The backend sanitizes the filename (`Path(file.filename).name`, path-traversal guarded).
- **`google-generativeai` is deprecated** — importing/using it prints a `FutureWarning`; the code works as-is.
  `PROJECT_STATE.md` notes an optional migration to `google-genai`.
- **Free-tier Gemini rate limits** apply on live `gemini` runs; the fixture provider (default for the demo) is
  key-free and instant, which is why the verify commands above use it.
- **`DECISIONS.md`** lists a PO-bypass cumulative-per-vendor cap and Segregation-of-Duties rule that are **not**
  implemented in code (see `03`).
- **`PROJECT_STATE.md` repo-layout block is stale** — it labels `main.py` / an `api/` package as "not yet built"
  and engine/store as "in flight". In reality all are built and there is no `backend/app/api/` directory
  (routes live in `main.py`). Its later "build status" section correctly says everything is built and verified.
- The **Verdict → PayFlow rename** has not landed: `frontend/src/components/Layout.tsx`, `backend/app/main.py`
  (`FastAPI(title="Verdict")`), `frontend/index.html`, `README.md`, and the DB filename `verdict.db` still say
  "Verdict". Confirm: `grep -rn "Verdict" frontend/src/components/Layout.tsx backend/app/main.py`.
