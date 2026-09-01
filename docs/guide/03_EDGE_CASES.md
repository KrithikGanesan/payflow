# 03 · Edge Cases (the fact-check table)

> Product name **PayFlow**; code still says "Verdict" in places (see `00_README.md`).

This is the primary fact-check artifact: the happy path + every corpus edge case, mapped to the rule +
threshold that fires it, the **expected decision + reason code from `data/fixtures/manifest.json`**, where
it's implemented, and the test that covers it. Run `scripts/smoke_test.py` to confirm all 13 live
(see `04_FACT_CHECK.md`).

Corpus scoreboard (manifest): **4 APPROVE · 8 HOLD · 1 REJECT** (13 total).

| # | Corpus file | Scenario | Rule + threshold | Expected (manifest) | Reason code emitted | Implemented in | Covering test |
|---|-------------|----------|------------------|---------------------|---------------------|----------------|---------------|
| 1 | `01_clean_exact.pdf` | Clean 3-way match | Vendor match ≥92; subtotal == PO ($12,000); 3-way vs GR-9001; GL full-conf | **APPROVE** | `OK_MATCH` / `OK_CLEAN` | `matching.check`, `tolerance.check`, `vendors.check`, `decide` | `test_decide.py::test_happy_path_clean_match_approves` |
| 2 | `02_clean_tolerance.pdf` | Within tolerance | Subtotal $4,512 vs PO-1002 $4,500 = +$12/+0.27%, within ±1% **and** ≤$25 | **APPROVE** | `OK_MATCH` | `tolerance.check` (`TOLERANCE_PCT`/`TOLERANCE_ABS`) | `test_tolerance.py::test_within_abs_and_pct_auto_clears` |
| 3 | `03_split_po_partial.pdf` | Split-PO partial billing | PO-1003 already billed $20k of $60k; this $20k → cum $40k ≤ $60k×1.01 | **APPROVE** | `OK_MATCH` | `matching.check` + `matching.cumulative_after` | `test_matching.py::test_split_po_within_cumulative_ok`, `test_decide.py::test_edge_split_po_within_cap_approves` |
| 4 | `04_fuzzy_duplicate.pdf` | Fuzzy duplicate | Same vendor+amount ($7,500) as historical INV-WC-2001, date within ±7d, diff invoice# → weighted score ≥70 | **HOLD** | `HOLD_DUP_FUZZY` | `duplicates.check` (`DUP_FUZZY_HOLD_SCORE=70`) | `test_duplicates.py::test_fuzzy_resubmission_holds`, `test_decide.py::test_edge_fuzzy_duplicate_holds` |
| 5 | `05_tax_over_tolerance.pdf` | Amount over PO (tax nuance) | Goods subtotal $10,300 vs PO-1004 $10,000 = +3.0%, over tighter bound ($25). Tax/freight excluded | **HOLD** | **`HOLD_OVERBILL`** (also `HOLD_TOLERANCE` fires) — see caveat | `matching.check` (cum $10,300 > cap $10,100) + `tolerance.check` | `test_tolerance.py::test_tolerance_hold_cites_both_values`, `test_decide.py::test_edge_over_tolerance_holds` |
| 6 | `06_scanned_lowconf.pdf` | Scanned / low confidence | Image-only PDF, per-field confidence < 0.80 | **HOLD** | `HOLD_LOW_CONFIDENCE` | `policy.confidence_gate` (`CONFIDENCE_GATE=0.80`) | `test_policy.py::test_low_confidence_holds`, `test_decide.py::test_edge_low_confidence_holds` |
| 7 | `07_po_bypass_small.pdf` | PO-bypass under $500 | No PO, $ < $500, approved + bypass vendor (Umbrella/Facilities) → approve + notify finance | **APPROVE** | `OK_BYPASS` (+ `bypass_notice`) | `policy.po_bypass` (`PO_BYPASS_LIMIT=500`) | `test_policy.py::test_bypass_eligible_approves_and_notifies`, `test_decide.py::test_edge_po_bypass_approves_and_notifies` |
| 8 | `08_name_mismatch.pdf` | Vendor name mismatch | "Acme Corp" vs master "Acme Corporation Inc."; blend score ≈75.5 < 80 floor | **HOLD** | **`HOLD_VENDOR_UNAPPROVED`** (not `HOLD_VENDOR_FUZZY`) — see caveat | `vendors.check` (`VENDOR_MATCH_FLOOR=80`) | `test_vendors.py::test_no_confident_match_holds_as_unapproved`, `test_mid_band_fuzzy_match_holds_for_review` |
| 9 | `09_unapproved_vendor.pdf` | Unapproved vendor | Ghost Supplies LLC (V008) `approved=false` (matches PO-1007 otherwise) | **HOLD** | `HOLD_VENDOR_UNAPPROVED` | `vendors.check` (approved-vendor gate) | `test_vendors.py::test_unapproved_vendor_holds`, `test_decide.py::test_precedence_hold_beats_approve` |
| 10 | `10_spend_anomaly.pdf` | Spend anomaly | $40,000 vs Cyberdyne history mean ≈$2,050 / max $2,200 → >5× mean & >2× max (matches PO-1006/GR-9006) | **HOLD** | `HOLD_ANOMALY` | `anomaly.check` (`5×`/`2×`, min 2 history) | `test_anomaly.py::test_burst_over_mean_multiplier_holds`, `test_over_max_multiplier_holds`, `test_decide.py::test_edge_spend_anomaly_holds` |
| 11 | `11_credit_memo.pdf` | Credit memo | Negative total → routed separately, skips financial matching | **HOLD** | `HOLD_CREDIT_MEMO` | `policy.credit_memo` | `test_policy.py::test_credit_memo_doctype_holds`, `test_negative_total_holds` |
| 12 | `12_currency_mismatch.pdf` | Currency mismatch | Invoice EUR vs PO-1005 USD | **HOLD** | `HOLD_CURRENCY` | `policy.currency` | `test_policy.py::test_currency_mismatch_holds` |
| 13 | `13_exact_duplicate.pdf` | Exact duplicate | Exact match of already-paid INV-WC-2001 (same vendor/#/amount/date) | **REJECT** | `REJECT_DUP_EXACT` | `duplicates.check` (exact key) | `test_duplicates.py::test_exact_duplicate_rejects`, `test_decide.py::test_reject_exact_duplicate` |

## Additional behaviors covered by tests (not in the 13-file corpus)

| Behavior | Rule + threshold | Decision / code | Implemented in | Covering test |
|----------|------------------|-----------------|----------------|---------------|
| Over-billing (split-PO) | cum billed > PO×1.01 | HOLD · `HOLD_OVERBILL` | `matching.check` | `test_matching.py::test_split_po_over_billing_holds`, `test_decide.py::test_edge_split_po_overbilling_holds` |
| 3-way, billed > goods received | billed > GR×1.01 | HOLD · `HOLD_OVERBILL` | `matching.check` | `test_matching.py::test_three_way_billing_exceeds_goods_received_holds` |
| 3-way, missing goods receipt | `requires_goods_receipt` but no GR | HOLD · `HOLD_OVERBILL` | `matching.check` | `test_matching.py::test_three_way_missing_goods_receipt_holds` |
| Tolerance $-bound on large PO | +$30 on $100k = +0.03% but > $25 | HOLD · `HOLD_TOLERANCE` | `tolerance.check` | `test_tolerance.py::test_over_dollar_bound_holds_even_if_under_pct` |
| Tolerance %-bound on small PO | +$5 on $100 = +5% though only $5 | HOLD · `HOLD_TOLERANCE` | `tolerance.check` | `test_tolerance.py::test_over_pct_bound_holds_even_if_under_dollar_on_small_po` |
| Bank-change fraud flag | remit_to_bank ≠ vendor master hash | HOLD · `HOLD_BANK_CHANGE` (+ `fraud_flag` note, routes $150k → CFO) | `vendors.check`, `decide` | `test_vendors.py::test_bank_change_flag`, `test_decide.py::test_bank_change_routes_high_dollar_to_cfo` |
| GL coding low confidence | vendor lacks account/cost-centre defaults | HOLD · `HOLD_CODING_LOW_CONF` | `coding.predict` | `test_coding.py::test_missing_defaults_low_confidence_holds`, `test_no_vendor_low_confidence_holds`, `test_partial_defaults_holds` |
| Arithmetic failure | `validation` key False | HOLD · `HOLD_LOW_CONFIDENCE` | `policy.confidence_gate` | `test_policy.py::test_failed_arithmetic_holds` |
| No PO ≥ bypass limit | no PO, amount ≥ $500 | REJECT · `REJECT_NO_PO_OVER_BYPASS` | `policy.po_bypass` | `test_policy.py::test_no_po_over_bypass_limit_rejected` |
| No PO under limit, not bypass-eligible | no PO, < $500, vendor not bypass | HOLD · `HOLD_MATERIALITY` | `policy.po_bypass` | `test_policy.py::test_under_limit_not_bypass_eligible_holds` |
| PO expired/closed | `status` in {expired, closed} | REJECT · `REJECT_PO_EXPIRED` | `policy.po_status` | `test_policy.py::test_expired_po_rejected`, `test_closed_po_rejected` |
| Not an invoice | `doc_type` STATEMENT/OTHER | REJECT · `REJECT_NOT_INVOICE` | `policy.document_type` | `test_policy.py::test_statement_rejected`, `test_other_doc_rejected` |
| Missing critical field | vendor/inv#/date/total null | REJECT · `REJECT_MISSING_CRITICAL` | `policy.missing_critical` | `test_policy.py::test_missing_total_rejected`, `test_missing_vendor_name_rejected` |
| Split-to-avoid-threshold | ≥2 invoices each <$5k within 14d sum ≥$5k | HOLD · `HOLD_SPLIT_THRESHOLD` | `policy.split_threshold` | (logic in `policy.py`; exercised via `decide` paths) |
| Precedence: REJECT beats HOLD | unapproved vendor (HOLD) + exact dup (REJECT) | REJECT | `decide._precedence` | `test_decide.py::test_precedence_reject_beats_hold` |
| Precedence: HOLD beats APPROVE | clean match + unapproved vendor | HOLD | `decide._precedence` | `test_decide.py::test_precedence_hold_beats_approve` |

## Caveats worth knowing (fully honest)
- **Case 05 emits `HOLD_OVERBILL`, not `HOLD_TOLERANCE`.** Both gates fire (subtotal $10,300 vs PO $10,000:
  cum $10,300 > cap $10,100, and variance $300 > allowed $25), but `matching` runs before `tolerance` in
  `decide()`, so the first/top non-INFO reason is `HOLD_OVERBILL`. **Decision is HOLD either way** — matches
  the manifest. (Verified against `data/fixtures/00722fdb….json`: PO-1004, subtotal 10300, tax 500, total 11100.)
- **Case 08 emits `HOLD_VENDOR_UNAPPROVED`, not `HOLD_VENDOR_FUZZY`.** "Acme Corp" vs "Acme Corporation Inc"
  scores ≈75.5 (token_set_ratio+Jaro-Winkler blend), **below the 80 floor**, so it's treated as no confident
  match rather than the 80–92 fuzzy band. **Decision is HOLD** — matches the manifest. (Verified by computing
  the rapidfuzz score directly.) `PROJECT_STATE.md` already flags both as "reason-code precision" polish items.
- **`DECISIONS.md` lists two rules not in the code:** a PO-bypass *cumulative-per-vendor cap* (not implemented —
  `policy.po_bypass` has no cap) and *Segregation of Duties* (creator ≠ approver; not enforced anywhere). The
  split-threshold and bank-change controls it lists **are** implemented.
