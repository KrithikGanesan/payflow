# 06 · Edge Cases (deep, per scenario)

> PayFlow; code still says "Verdict" in places (see `00_INDEX.md`). Verified live: `smoke_test.py` = **15/15**.

Each row: input (from the ground-truth fixture) → the gate that fires (engine `module.function`) → reason code +
key `values` → decision. Thresholds (from `config.py`) are what make each one deterministic. Corpus scoreboard:
**5 APPROVE · 9 HOLD · 1 REJECT** (15 total).

| # | File / vendor | Key input | Gate (function) | Reason code + values | Decision |
|---|---------------|-----------|-----------------|----------------------|----------|
| 01 | `01_clean_exact` · Acme (V001) | PO-1001 $12,000, **3-way**, GR-9001 $12,000; inv 12,000 | `matching.check` 3-way + `tolerance.check` | `OK_MATCH` (billed 12,000 ≤ cap 12,120; received 12,000) | **APPROVE** |
| 02 | `02_clean_tolerance` · Globex (V002) | PO-1002 $4,500, 3-way GR-9002 $4,500; subtotal 4,500 / tax 12 / total 4,512 | `tolerance.check` (tax excluded) | `OK_MATCH` (variance $0 on subtotal; $12 is tax) | **APPROVE** |
| 03 | `03_split_po_partial` · Initech (V003) | PO-1003 $60,000, cum **$20,000**; this $20,000 → cum $40,000 | `matching.check` (cumulative) | `OK_MATCH` (cum 40,000 ≤ 60,600); under-bill on tolerance is fine | **APPROVE** |
| 04 | `04_fuzzy_duplicate` · Wayne (V006) | inv **INV-WC-2099** $7,500 2026-06-18 vs history **INV-WC-2001** $7,500 2026-06-15 | `duplicates.check` (fuzzy) | `HOLD_DUP_FUZZY` — amount +40, date(3d)+20, invoice# JW +20 → **80 ≥ 70** | **HOLD** |
| 05 | `05_tax_over_tolerance` · Stark (V005) | PO-1004 $10,000 2-way; subtotal **$10,300** / tax 500 / total 11,100 | `matching.check` then `tolerance.check` | `HOLD_OVERBILL` (cum 10,300 > cap 10,100) **and** `HOLD_TOLERANCE` (+$300 > $25) | **HOLD** |
| 06 | `06_scanned_lowconf` · Tyrell (V011) | PO-1009 $6,000; **all field confidences 0.44–0.71** (scanned) | `policy.confidence_gate` | `HOLD_LOW_CONFIDENCE` (`low_fields`, lowest 0.44 < 0.80) | **HOLD** |
| 07 | `07_po_bypass_small` · Umbrella (V004) | **no PO**, $420, approved + `po_bypass_allowed` | `policy.po_bypass` | `OK_BYPASS` (420 < 500) + `bypass_notice`→finance | **APPROVE** |
| 08 | `08_name_mismatch` · "Acme Corp" | PO-1008; name "Acme Corp" vs "Acme Corporation Inc." | `vendors.check` | `HOLD_VENDOR_UNAPPROVED` (blend ≈75.5 < 80 floor → no confident match) | **HOLD** |
| 09 | `09_unapproved_vendor` · Ghost (V008) | PO-1007 $3,000; **V008 `approved=false`**, null GL defaults | `vendors.check` (+ `coding.predict`) | `HOLD_VENDOR_UNAPPROVED` (approved gate) + `HOLD_CODING_LOW_CONF` (conf 0.20) | **HOLD** |
| 10 | `10_spend_anomaly` · Cyberdyne (V007) | PO-1006 $40,000 3-way GR-9006 $40,000 (matches!); history mean ≈$2,050 / max $2,200 | `anomaly.check` | `HOLD_ANOMALY` (40,000 > 5×mean **and** > 2×max; `x_mean≈19.5`) | **HOLD** |
| 11 | `11_credit_memo` · Soylent (V010) | total **−$1,500**, `doc_type=CREDIT_MEMO` | `policy.credit_memo` | `HOLD_CREDIT_MEMO` — skips all financial gates | **HOLD** |
| 12 | `12_currency_mismatch` · Nakatomi (V009) | PO-1005 **USD**, invoice **EUR** $8,000 | `policy.currency` | `HOLD_CURRENCY` (`invoice_currency EUR ≠ po_currency USD`) | **HOLD** |
| 13 | `13_exact_duplicate` · Wayne (V006) | inv **INV-WC-2001** $7,500 2026-06-15 == paid history | `duplicates.check` (exact) | `REJECT_DUP_EXACT` (also `HOLD_OVERBILL` on PO-1011; REJECT wins) | **REJECT** |
| 14 | `14_multi_gr` · Hooli (V012) | PO-1013 $10,000 3-way; **GR-9013a $4,000 + GR-9013b $6,000**; inv $10,000 | `matching.check` 3-way on **summed** GR | `OK_MATCH` (received 10,000 "2 receipts"; 10,000 ≤ 10,100) | **APPROVE** |
| 15 | `15_awaiting_receipt` · Pied Piper (V013) | PO-1014 $8,000 **3-way, NO receipt yet**; inv $8,000 | `matching.check` 3-way, no GR | `HOLD_AWAITING_RECEIPT` (`this_invoice 8000, received_total null`) | **HOLD** |

## The two newest scenarios — full treatment

### 14 · Multi-GR (receipt summing) → APPROVE
**Why it's the strongest APPROVE:** it proves the matcher aggregates split deliveries instead of naïvely
comparing to one receipt.
- **Masters:** V012 Hooli Cloud Services Inc. (approved, GL 5010 / CC-200). PO-1013 = $10,000, `requires_goods_receipt=true`, cumulative 0. Receipts: **GR-9013a $4,000 (2026-08-19)** + **GR-9013b $6,000 (2026-08-26)**.
- **Orchestrator (`_gather_masters`)** calls `store.goods_receipts_for("PO-1013")` → both rows → sums to a single `GoodsReceipt(received_total=$10,000, gr_id="2 receipts", received_date=2026-08-26)`.
- **`matching.check` (3-way):** billed = subtotal $10,000; cap = 10,000×1.01 = **$10,100**; cumulative 10,000 ≤ cap; receipt present, `10,000 ≤ 10,000×1.01 = 10,100` → **`OK_MATCH`** ("Goods received $10,000 (2 receipts)").
- Vendor OK_MATCH, coding 0.95, currency USD, tolerance $0 variance, no history → no dup/anomaly. Precedence → **APPROVE**, routed to **director** ($10k = `5k-25k`).
- **Counterfactual:** matching only GR-9013a ($4,000) would give allowed $4,040 and flag `HOLD_OVERBILL` on a legitimate invoice — exactly the false positive summing prevents.

### 15 · Awaiting receipt → HOLD (not REJECT)
**Why it earns its own reason code:** a 3-way invoice that lands *before* the goods must not be paid yet, but
it also isn't wrong — the goods may be in transit. `HOLD`, never `REJECT`.
- **Masters:** V013 Pied Piper Data Corp (approved, GL 5010 / CC-200). PO-1014 = $8,000, `requires_goods_receipt=true`, cumulative 0, **no goods receipts on file**.
- **Orchestrator:** `goods_receipts_for("PO-1014")` → `[]` → `gr = None`.
- **`matching.check` (3-way, `goods_receipt is None`):** → **`HOLD_AWAITING_RECEIPT`** (`values: this_invoice 8000, received_total null`; rule `3-way: awaiting goods receipt`). Over-bill guard: cum 8,000 ≤ cap 8,080, so no `HOLD_OVERBILL`.
- Vendor/coding/currency/tolerance all pass. Precedence → **HOLD**, routed to **director**.
- **Contrast with over-billing:** a *present* receipt below the billed amount → `HOLD_OVERBILL` (mismatch); *no* receipt → `HOLD_AWAITING_RECEIPT` (timing). Different codes, same "don't pay yet" outcome, different remediation.

## The demo upload set (`~/Desktop/payflow_demo/`, live via Gemini)
Fresh PDFs (novel sha256 → real extraction), consistent with the seeded masters:

| Demo PDF | Vendor / PO | Amount | Fires | Decision |
|----------|-------------|--------|-------|----------|
| Acme $12,000 | V001 / PO-1001 (3-way, GR $12,000) | $12,000 | clean 3-way match | **APPROVE** |
| Stark $10,300 | V005 / PO-1004 (2-way, $10,000) | subtotal 10,300 (+ tax) | `HOLD_OVERBILL` + `HOLD_TOLERANCE` (goods +3% over PO; tax excluded) | **HOLD** |
| Cyberdyne $40,000 | V007 / PO-1006 (3-way, GR $40,000) | $40,000 | `HOLD_ANOMALY` (~20× vendor norm, though it matches the PO) | **HOLD** |
| Umbrella $385 | V004, no PO (bypass) | $385 | `OK_BYPASS` + `bypass_notice`→finance | **APPROVE** |

These mirror corpus scenarios 01/05/10/07 but as *unseen* PDFs, so the demo shows a genuine live Gemini
extraction (the `EXTRACTED` stage spinner) rather than a cached replay.

## Behaviors proven only by unit tests (not in the corpus)
`HOLD_BANK_CHANGE` (remit-to bank ≠ master; routes $150k → CFO), `HOLD_SPLIT_THRESHOLD` (siblings dodging the
$5k limit), `REJECT_PO_EXPIRED`, `REJECT_NOT_INVOICE`, `REJECT_MISSING_CRITICAL`, `REJECT_NO_PO_OVER_BYPASS`,
`HOLD_MATERIALITY`, `HOLD_VENDOR_FUZZY` (80–92 band), and the tolerance $/% bound edges — see
`backend/tests/test_*.py` (70 tests) and `02_ENGINE_DESIGN.md`.
