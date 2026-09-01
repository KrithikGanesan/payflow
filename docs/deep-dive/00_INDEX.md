# PayFlow — Technical Deep-Dive

> Product name **PayFlow**; the code still says "Verdict" in places (sidebar brand, `FastAPI(title="Verdict")`,
> `README.md`, `index.html`, DB file `verdict.db`, repo folder) until the rename lands. Read "Verdict" as "PayFlow".

## What this set is
This is the **full internals** of PayFlow — the engineering reference. For the quick, skimmable fact-check
version see **`../guide/`** (`00_README`…`04_FACT_CHECK`). This set goes deeper: every gate function, the exact
gate order, worked numeric traces, the run/SSE lifecycle, the extraction pipeline, and a per-scenario deep table.

## One-paragraph system summary
PayFlow turns a vendor **invoice PDF** into an **APPROVE / HOLD / REJECT** verdict with a complete reasoning
trail. A **FastAPI** backend resolves the PDF, extracts structured fields via **Google Gemini** vision + a
pdfplumber text layer (or a key-free **fixture** replay), validates the arithmetic, and runs a **pure-function
decision engine** of ~10 gates whose outcomes combine by **most-severe-wins precedence**. Runs, stages, and
notifications persist in **SQLite**. A staged orchestrator streams progress over **SSE** to a **React/Vite/TS/
Tailwind** frontend with 6 screens, including a **Live Run** stepper and a **Decision Flow** gate-by-gate trace.
Extraction is **content-addressed** (sha256 of the PDF), so corpus invoices replay deterministically while a
freshly uploaded PDF makes a real live Gemini call.

## How to read this set
| File | Read it for |
|------|-------------|
| `00_INDEX.md` | This map |
| `01_ARCHITECTURE.md` | The component/data-flow diagram, each part's job, tech-choice rationale, repo map |
| `02_ENGINE_DESIGN.md` | Every gate module: signature, rule, thresholds, reason codes, `values` keys; purity + TDD; full `config.py` table |
| `03_DECISION_LOGIC.md` | The 4 principles, exact gate order, precedence, DOA routing, notifications, + 3 fully worked traces |
| `04_RUN_FLOW.md` | End-to-end run lifecycle: resolve → extract → 6 stages → SSE event shapes → persistence → UI + `flowModel.deriveNodes` |
| `05_EXTRACTION.md` | Gemini + text layer, forced JSON schema, fixture provider, cache, validation + `_overall` confidence |
| `06_EDGE_CASES_DEEP.md` | All 15 corpus scenarios + the demo set, traced input → gate → reason → decision (multi-GR + awaiting-receipt in full) |

## Verify anything (no key needed)
```bash
EXTRACTION_PROVIDER=fixture ./.venv/bin/python scripts/smoke_test.py   # 15/15 corpus vs manifest
./.venv/bin/python -m pytest backend/tests -q                          # 70 engine tests
```
Current state confirmed while writing this set: **15/15 integration green, 70 tests green.**

Related: `../guide/` (quick version), `../knowledge/` (living handoff notes — some drift from code; see `../guide/04_FACT_CHECK.md`).
