# Verdict — Invoice-to-Decision · Design Spec
_Case study: Zamp AI Solutions Associate · PS-1 Finance/AP · 2026-08-30_

## 1. What it is
A vendor invoice (PDF) goes in. A clear **APPROVE / HOLD / REJECT** decision comes out —
with every step and every reason visible. Optimised for **judgment + explainability**,
not code volume. The product hands an AP clerk a *pre-investigated exception with evidence*,
not a black-box verdict.

## 2. Decision philosophy (the spine)
1. **Asymmetric risk → bias to HOLD.** A wrong auto-approve loses real, hard-to-recover money;
   an unnecessary hold costs ~2 min of a clerk's time. When uncertain: HOLD. REJECT only when
   unambiguously wrong.
2. **Scrutiny scales with Confidence × Materiality.** Extraction confidence AND dollar amount
   both drive how much human attention an invoice gets.
3. **Precedence — most-severe outcome wins.** Gates are ordered; one failed gate downgrades the
   whole decision. A clean invoice from an unapproved vendor still HOLDs.
4. **Every decision cites policy + values.** e.g. "HOLD · total $10,300 vs PO $10,000 = +3.0%,
   over ±1% tolerance; variance = $300 freight not on PO."

Goal metric: maximise **straight-through-processing (STP) rate** while catching 100% of risky items.

## 3. Pipeline (authentic AP lifecycle)
Received → **Extracted** (Gemini vision + text layer) → **Coded** (GL account + cost centre) →
**Matched** (2-way services / 3-way goods: PO ↔ invoice ↔ goods receipt) → **Validated**
(arithmetic, tolerance, duplicate, vendor, fraud, anomaly) → **Decided** (verdict + routing).
Artifacts named as AP does: vendor master, PO, goods receipt (GRN), voucher, remittance advice.

## 4. Checks (gates)
### BUILD (demo runs on these)
- Extraction + per-field confidence gate (never auto-approve on low confidence / failed arithmetic)
- 2-way / 3-way match (goods vs services) with cumulative-billing over-billing guard (split-PO)
- Price/total tolerance: **±1% AND ≤ $25** auto-clears; beyond → HOLD (quantity tolerance separate)
- **GL coding** (predict account + cost centre from vendor/history; low confidence → HOLD)
- Duplicate: exact key (vendor + invoice# + amount + date-proximity) → REJECT; fuzzy resubmission ≥70 → HOLD
- Approved-vendor gate + fuzzy name match (token_set + Jaro-Winkler; ≥92 auto / 80–92 HOLD / <80 HOLD)
- PO-bypass: < $500, approved vendor, bypass category → APPROVE **+ notify finance**; cumulative per-vendor cap; still coded + approver
- **Spend anomaly** vs vendor history (sudden burst → HOLD)
- Credit-memo (negative invoice) handling — routed separately
- Decision engine w/ precedence + **approval routing by dollar band (DOA)**; SoD boundary
- Immutable audit trail (stage, rule, values compared, actor, timestamp)

### BUILD IF TIME
- Remit-to **bank-detail-change flag** (compare vs vendor master) — highest-dollar fraud vector
- Tax sanity check (rate plausibility / reverse-charge awareness)
- Early-payment-discount capture (recommendation on APPROVE — value-add, not a gate)
- Split-to-avoid-threshold flag (count≥2 · each<limit · sum≥limit)
- Document-type gate (is it even an invoice?)

### DESIGNED, SCOPED OUT (interview talking points)
Sanctions/OFAC screening · W-9/1099 tracking · retainage · month-end accruals ·
full statement reconciliation · learning-from-corrections loop.

## 5. Decision states & precedence (most-severe wins)
- **REJECT**: exact duplicate · PO expired/closed · missing critical field · not an invoice
- **HOLD (fraud/compliance)**: unapproved/ghost vendor · bank-change · split-threshold
- **HOLD (financial)**: over tolerance · over-billing · low confidence · low-confidence coding · anomaly · credit memo
- **APPROVE**: clean match, or PO-bypass under threshold (+ notify)
Approval routing by amount: <$5k manager · $5k–25k director · $25k–100k VP · >$100k CFO/dual.
SoD: the actor that creates a vendor / changes bank detail can never also approve payment.

## 6. Featured demo edge cases (each = a different kind of judgment)
1. Split-PO partial billing (stateful) 2. Fuzzy duplicate (fraud) 3. Tax-over-tolerance (financial nuance)
4. Scanned / low-confidence (graceful degradation) 5. PO-bypass + notify (policy) 6. Spend anomaly (fraud instinct)

## 7. Architecture
- **Backend**: FastAPI (Python 3.13). Orchestrator runs stages, streams SSE events, persists runs.
- **Extraction**: provider-agnostic interface — `gemini` (default) | `ollama` | `fixture`.
  Clean PDFs feed text layer + image; scanned PDFs feed image (Gemini OCRs). Cached by file hash.
- **Decision engine**: pure functions, no I/O — fully unit-testable (TDD). This is the defensible core.
- **DB**: SQLite (po_master, vendor_master, goods_receipts, vendors' historical invoices, runs, run_stages, notifications).
- **Frontend**: React + Vite + TS + Tailwind + shadcn/ui; Recharts; react-pdf. SSE for live run.

## 8. UI (graded)
Screens: **Live Run** (stepper Captured→Extracted→Coded→Matched→Validated→Decided; side-by-side
PDF ↔ fields + confidence badges; verdict card w/ reasons), **Dashboard** (STP rate, exception
rate + top reasons, cycle time, status donut, aging, spend by vendor/dept), **Audit Trail /
Run detail**, **History**, **Exception Queue** (approve-with-reason). Neutral canvas, one indigo
accent, status colours reserved for meaning, tabular/monospace numerals.

## 9. Test data
Generated corpus (~10–12 invoice PDFs + PO master + vendor master + goods receipts + history),
each invoice crafted to trigger one path; one rasterised scanned image. `seed demo` one-click.

## 10. Reliability
Extraction cached per file hash → live-capable but replay-deterministic. Fixture provider means
the app runs fully even with no key. `./demo` boots backend + frontend in one command.

## 11. Non-goals
No real payment execution. No ERP write-back. No live vendor emails (notifications simulated in-app).
