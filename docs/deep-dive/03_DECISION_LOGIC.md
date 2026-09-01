# 03 · Decision Logic

> PayFlow; code still says "Verdict" in places (see `00_INDEX.md`). Everything here is `backend/app/engine/decide.py` + `policy.py`.

## The four principles
1. **Asymmetric risk → bias to HOLD.** A wrong auto-approve loses real money; an unnecessary hold costs a clerk ~2 minutes. When uncertain → **HOLD**; **REJECT** only when unambiguously wrong (not an invoice, missing critical field, expired PO, exact duplicate, no-PO over the bypass ceiling).
2. **Scrutiny scales with Confidence × Materiality.** Extraction/coding confidence gates a HOLD; dollar amount drives the DOA routing band. `_overall_confidence = round(min(min(extract.confidence.values()), gl.confidence), 4)`.
3. **Most-severe-wins precedence.** Gates are independent; the worst outcome across all of them decides. One red flag beats ten green checks.
4. **Cite the numbers.** Every `Reason` carries a plain-English `message` and a `values` dict of the exact figures compared — the audit trail and the Decision Flow chips read straight from it.

## The exact gate order in `decide()`
`decide(extract, vendors, po, goods_receipt, historical_invoices)`:

| Step | Call | Notes |
|------|------|-------|
| 0 | `policy.document_type(extract) + policy.missing_critical(extract)` | **If non-empty → return REJECT immediately** (short-circuit; skips everything below). |
| 1 | `_run_vendor(extract, vendors)` → `vendors.check` | Returns reasons **and** the matched vendor (used by coding/anomaly/bypass). Lazy import avoids the `vendors` param shadowing the module. |
| 2 | `coding.predict(extract, matched_vendor, historical)` | GL coding + `HOLD_CODING_LOW_CONF`. |
| 3 | `policy.po_status(po)` | `REJECT_PO_EXPIRED`. |
| 4 | `policy.credit_memo(extract)` | If it fires, **financial gates below are skipped** (`if not cm_reasons`). |
| 5 | `policy.confidence_gate(extract)` | Arithmetic-fail or low per-field confidence (ignores `_overall`). |
| 6 | `policy.currency(extract, po)` | `HOLD_CURRENCY`. |
| 7 | `duplicates.check(extract, historical, vendor_id)` | Exact (REJECT) or fuzzy (HOLD). |
| 8 | `matching.check(extract, po, goods_receipt)` *(not credit memo)* | 2-/3-way, over-bill, awaiting-receipt. |
| 9 | `tolerance.check(extract, po)` *(not credit memo)* | Subtotal vs PO. |
| 10 | `matching.cumulative_after(extract, po)` *(if po)* | Stored on the result. |
| 11 | `policy.po_bypass(extract, matched_vendor, po)` *(not credit memo)* | No-PO path; may add a `bypass_notice`. |
| 12 | `anomaly.check(extract, same-vendor history)` *(not credit memo)* | `[]` history for an unmatched vendor. |
| 13 | `policy.split_threshold(extract, same-vendor history)` *(not credit memo)* | `HOLD_SPLIT_THRESHOLD`. |
| — | `_precedence(reasons)` | See below. |
| — | append `OK_CLEAN` | **Only if** decision is APPROVE **and** there is no INFO reason yet. |
| — | routing + notifications | `route_for`/`materiality_band`; `approver_route` note for HOLD/APPROVE; `fraud_flag` note if any `HOLD_BANK_CHANGE`. |

Steps 1–7 always run (no early-reject). Steps 8–13 run only when it isn't a credit memo. Duplicates (7) runs before matching so an exact-dup REJECT is collected alongside any matching HOLD — precedence then picks REJECT.

## Precedence
```python
def _precedence(reasons):
    sev = {r.severity for r in reasons}
    if Severity.REJECT in sev: return Decision.REJECT
    if Severity.HOLD   in sev: return Decision.HOLD
    return Decision.APPROVE
```
Any REJECT-severity reason → **REJECT**; else any HOLD → **HOLD**; else **APPROVE**. `INFO` reasons
(`OK_MATCH`, `OK_BYPASS`, `OK_CLEAN`) never downgrade — they are the evidence that a gate passed.

## Routing (DOA) & materiality
`amount = total or subtotal`. Bands from `config.py`:

| Amount | `materiality_band` | `route_for` |
|--------|--------------------|-------------|
| < $5,000 | `<5k` | manager |
| $5,000–24,999.99 | `5k-25k` | director |
| $25,000–99,999.99 | `25k-100k` | VP |
| ≥ $100,000 | `>100k` | CFO |

## Notifications (`DecisionResult.notifications`)
| Type | Recipient | When |
|------|-----------|------|
| `bypass_notice` | finance | `OK_BYPASS` fired (auto-approve a no-PO small spend — "nothing silent") |
| `approver_route` | the DOA role | Any HOLD or APPROVE (routes `$amount (band)` to manager/director/VP/CFO) |
| `fraud_flag` | ap-controls | Any `HOLD_BANK_CHANGE` (verify vendor bank out-of-band) |
| `human_decision` | audit | A human override via `POST /runs/{id}/decision` (added in `main.py`, not the engine) |

---

## Worked trace 1 — APPROVE (multi-GR receipt summing)
**Input** (`14_multi_gr.pdf`): Hooli Cloud Services Inc. · INV `HL-2026-041` · 2026-08-27 · **PO-1013** · USD ·
subtotal **$10,000** / tax 0 / total **$10,000** · all field confidences 0.97.
**Masters:** V012 Hooli (approved, GL 5010 / CC-200). PO-1013 = $10,000, **3-way**, cumulative 0. Two receipts
**GR-9013a $4,000 + GR-9013b $6,000**. No V012 history.
**Orchestrator** sums the receipts → one `GoodsReceipt(received_total=$10,000, gr_id="2 receipts")`.

| Gate | Result |
|------|--------|
| document_type / missing_critical | pass (INVOICE, all critical fields present) |
| vendor | name_score(Hooli inv vs "hooli cloud services inc") ≥ 92, approved → **OK_MATCH** (INFO) |
| coding | account 5010 + cost centre CC-200 → conf 0.95 ≥ 0.80 → no hold |
| po_status | PO open → pass |
| credit_memo | total ≥ 0 → no |
| confidence_gate | min field conf 0.97 ≥ 0.80, arithmetic ok → pass |
| currency | USD == USD → pass |
| duplicates | no V012 history → `[]` |
| matching (3-way) | billed 10,000; cap 10,000×1.01 = **10,100**; cum 10,000 ≤ cap; receipt present, 10,000 ≤ 10,000×1.01 = 10,100 → **OK_MATCH** (INFO, "Goods received $10,000 (2 receipts)") |
| tolerance | 10,000 vs 10,000, variance $0 ≤ allowed $25 → **OK_MATCH** (INFO) |
| po_bypass | PO present → skipped |
| anomaly / split | empty V012 history → `[]` |

**Precedence:** severities = {INFO} → **APPROVE**. INFO reasons already exist, so `OK_CLEAN` is **not** added.
`overall_confidence = min(0.97, 0.95) = 0.95`. amount $10,000 → band `5k-25k` → **routed to director**
(`approver_route` note). *Why it matters:* a naïve matcher comparing the invoice to only GR-9013a ($4,000)
would wrongly flag over-billing; summing the receipts is what makes this a clean approve.

## Worked trace 2 — HOLD (Stark: subtotal over PO, tax excluded)
**Input** (`05_tax_over_tolerance.pdf`): Stark Logistics LLC · INV `STK-7781` · 2026-08-25 · **PO-1004** · USD ·
subtotal **$10,300** / tax **$500** / total **$11,100** · confidences 0.97.
**Masters:** V005 Stark (approved, GL 5050 / CC-200). PO-1004 = $10,000, **2-way** (no GR), cumulative 0.

| Gate | Result |
|------|--------|
| vendor | matches V005, approved → OK_MATCH (INFO) |
| coding | 5050 + CC-200 → 0.95 → no hold |
| confidence_gate / currency | pass / pass |
| duplicates | no matching Stark history at this amount → `[]` |
| **matching (2-way)** | billed = subtotal **10,300**; cap 10,000×1.01 = **10,100**; cum 10,300 **>** 10,100 → **`HOLD_OVERBILL`** (`values: cumulative_after 10300, po_total 10000, cap 10100`) |
| **tolerance** | variance 10,300 − 10,000 = **+300**; allowed = min(25, 100) = **25**; 300 > 25 → **`HOLD_TOLERANCE`** (`values: subtotal 10300, po_total 10000, variance 300, pct 0.03, allowed 25`) |
| po_bypass / anomaly / split | skipped-or-empty |

**Precedence:** {INFO, HOLD} → **HOLD**. Two HOLDs fire; `matching` runs before `tolerance`, so the first
non-INFO reason (the UI "top reason") is **`HOLD_OVERBILL`**. amount = total **$11,100** → band `5k-25k` →
routed to **director**. *Narration:* the $11,100 total includes $500 tax, but the engine compares only the
**$10,300 of goods** to the $10,000 PO — still +3%, so it holds; the tax was never the problem.

## Worked trace 3 — REJECT (exact duplicate)
**Input** (`13_exact_duplicate.pdf`): Wayne Consulting Group · INV **`INV-WC-2001`** · **2026-06-15** ·
PO-1011 · USD · subtotal/total **$7,500** · confidences 0.97.
**Masters:** V006 Wayne (approved). History has **`INV-WC-2001` $7,500 2026-06-15** (already paid). PO-1011 =
$7,500, 2-way, **cumulative_billed already $7,500** (fully billed).

| Gate | Result |
|------|--------|
| vendor / coding / confidence / currency | all pass |
| **duplicates (exact key)** | normalized invoice# equal, `|7,500 − 7,500| ≤ 0.01`, dates 0 days apart ≤ 7 → **`REJECT_DUP_EXACT`** (`values: matched_invoice INV-WC-2001, amount 7500, invoice_date/prior_date 2026-06-15`) |
| matching (2-way) | cum 7,500 + 7,500 = 15,000 > 7,500×1.01 = 7,575 → also **`HOLD_OVERBILL`** |
| tolerance | 7,500 vs 7,500 → OK_MATCH (INFO) |

**Precedence:** {INFO, HOLD, REJECT} → **REJECT**. The exact-duplicate REJECT dominates the over-billing HOLD —
a re-post of an already-paid invoice is hard-blocked, not merely held. amount $7,500 → band `5k-25k`, but no
`approver_route` note is added for REJECT (only HOLD/APPROVE route).
