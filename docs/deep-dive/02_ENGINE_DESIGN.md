# 02 · Engine Design (gate internals)

> PayFlow; code still says "Verdict" in places (see `00_INDEX.md`). All references are `module.function` in `backend/app/engine/`.

## Design invariants
- **Pure functions, no I/O.** Every gate takes contracts objects and returns `list[Reason]` (a few also return a matched entity or notifications). No DB, no network, no clock reads except `date` parsing. This makes each gate deterministic and independently unit-testable.
- **Reasons carry evidence.** Each `Reason` has `code` (`ReasonCode`), `severity` (`INFO`/`HOLD`/`REJECT`), a plain-English `message` that cites the numbers, a short `rule` string, and a `values` dict (the machine-readable numbers used — surfaced as chips in the UI).
- **Thresholds live only in `config.py`.** No gate hard-codes a number; every bound references a named constant, so the rules stay auditable and the values testable.
- **TDD.** `backend/tests/` has **70 tests** — per-gate unit tests plus integration tests through `decide()`. Counts: `test_policy` 22, `test_decide` 14, `test_matching` 7, `test_tolerance` 7, `test_duplicates` 6, `test_vendors` 6, `test_coding` 4, `test_anomaly` 4. Factories in `conftest.py` (`make_extract/vendor/po/gr/hist`).

## The full `config.py` threshold table

| Constant | Value | Used by | Meaning |
|----------|-------|---------|---------|
| `TOLERANCE_PCT` | `0.01` | tolerance, matching | ±1% price band |
| `TOLERANCE_ABS` | `25.0` | tolerance | ≤ $25 absolute band (auto-clear within the **tighter** of the two) |
| `PO_BYPASS_LIMIT` | `500.0` | policy.po_bypass | No-PO auto-approve ceiling (strictly under) |
| `DUP_WEIGHT_AMOUNT` | `40` | duplicates | Weight when amount matches |
| `DUP_WEIGHT_DATE` | `20` | duplicates | Weight when date within window |
| `DUP_WEIGHT_INVOICE_NO` | `20` | duplicates | Weight when invoice# JW ≥ threshold |
| `DUP_WEIGHT_LINE_ITEMS` | `20` | duplicates | Weight when line-items token_set ≥ threshold |
| `DUP_AMOUNT_PCT` | `0.01` | duplicates | Amounts equal within ±1% |
| `DUP_DATE_WINDOW_DAYS` | `7` | duplicates | ± days counted as "same period" |
| `DUP_INVOICE_JW_THRESHOLD` | `0.90` | duplicates | Jaro-Winkler ≥ this scores the invoice-no weight |
| `DUP_LINE_ITEMS_THRESHOLD` | `90` | duplicates | token_set_ratio (0–100) ≥ this scores lines |
| `DUP_FUZZY_HOLD_SCORE` | `70` | duplicates | Total weighted score ≥ this → `HOLD_DUP_FUZZY` |
| `DUP_EXACT_AMOUNT_ABS` | `0.01` | duplicates | Exact-dup amount equal to the cent |
| `DUP_EXACT_DATE_WINDOW_DAYS` | `7` | duplicates | Exact-dup date proximity |
| `VENDOR_MATCH_AUTO` | `92.0` | vendors | ≥ → confident auto-match |
| `VENDOR_MATCH_FLOOR` | `80.0` | vendors | 80–92 → fuzzy HOLD; < 80 → no confident match |
| `CONFIDENCE_GATE` | `0.80` | policy.confidence_gate | Per-field extraction confidence floor |
| `CODING_CONFIDENCE_GATE` | `0.80` | coding | GL coding confidence floor |
| `CODING_CONF_FULL` | `0.95` | coding | Both account + cost centre known |
| `CODING_CONF_PARTIAL` | `0.55` | coding | One of the two known |
| `CODING_CONF_NONE` | `0.20` | coding | Neither known |
| `ANOMALY_MEAN_MULTIPLIER` | `5.0` | anomaly | > 5× vendor mean → burst |
| `ANOMALY_MAX_MULTIPLIER` | `2.0` | anomaly | > 2× vendor historical max → burst |
| `ANOMALY_MIN_HISTORY` | `2` | anomaly | Min prior invoices before flagging |
| `SPLIT_WINDOW_DAYS` | `14` | policy.split_threshold | Sibling-invoice window |
| `SPLIT_THRESHOLD` | `5000.0` | policy.split_threshold | Approval limit being dodged |
| `DOA_MANAGER` | `5000.0` | policy routing | < $5k → manager |
| `DOA_DIRECTOR` | `25000.0` | policy routing | $5k–25k → director |
| `DOA_VP` | `100000.0` | policy routing | $25k–100k → VP; > $100k → CFO |

---

## `matching.py` — 2-way / 3-way PO match + over-billing + awaiting-receipt
**`check(extract, po, goods_receipt) -> list[Reason]`** (also `cumulative_after(extract, po) -> float`, `_billed(extract)`).
- **No PO** → returns `[]` (no PO invoices are handled by `policy.po_bypass`).
- **Billed** = `subtotal` (fallback `total`). **Cumulative** = `po.cumulative_billed + billed`. **Cap** = `po.po_total × (1 + TOLERANCE_PCT)`.
- **Over-billing guard:** `cum > cap + 1e-9` → **`HOLD_OVERBILL`**. `values`: `cumulative_after, po_total, prior_billed, this_invoice, cap`.
- **3-way** (`po.requires_goods_receipt`):
  - **No receipt** → **`HOLD_AWAITING_RECEIPT`** ("invoice arrived before the goods; hold, not reject"). `values`: `this_invoice, received_total: null`.
  - **Receipt present** and `billed > received_total × (1 + TOLERANCE_PCT) + 1e-9` → **`HOLD_OVERBILL`** (rule `3-way match: billed ≤ goods received`). `values`: `this_invoice, received_total`.
- **Clean** (no reasons yet) → **`OK_MATCH`** (INFO), labelled `2-way`/`3-way`; includes `received_total` in `values` when a 3-way receipt exists.

> The orchestrator hands this a **single, summed** goods receipt across all receipts on the PO (see `04`), so a split delivery (GR-9013a $4k + GR-9013b $6k) matches a $10k invoice.

## `tolerance.py` — price/total tolerance vs PO
**`check(extract, po) -> list[Reason]`** (also `allowed_variance(po_total) = min(TOLERANCE_ABS, |po_total|·TOLERANCE_PCT)`).
- Compares invoice **subtotal** (fallback total) to `po.po_total` — **tax/freight excluded** so legitimate tax never trips it. No PO or no billed value → `[]`.
- `variance = billed − po_total`; `allowed` = the tighter bound.
- `variance ≤ allowed + 1e-9` → **`OK_MATCH`** (INFO). Under-billing (`variance < -allowed`) is a legit partial/split bill, never a hold.
- Else → **`HOLD_TOLERANCE`**. `values`: `subtotal, po_total, variance, pct, allowed`. Rule string: `tolerance ±1% AND ≤$25 (whichever tighter)`.

## `duplicates.py` — exact (REJECT) + fuzzy (HOLD)
**`check(extract, historical, vendor_id=None) -> list[Reason]`** (+ `normalize_invoice_no`, `_fuzzy_score`, `_line_fingerprint`).
- Amount = `total` (fallback subtotal). No amount or no history → `[]`. Considers **same-vendor** history only (when `vendor_id` given).
- **Exact key:** same normalized invoice# **and** `|amount − h.amount| ≤ DUP_EXACT_AMOUNT_ABS` **and** date within `DUP_EXACT_DATE_WINDOW_DAYS` (or unparseable) → **`REJECT_DUP_EXACT`**. `values`: `matched_invoice, amount, invoice_date, prior_date`.
- **Fuzzy score** (weights, each added if its condition holds): amount within `DUP_AMOUNT_PCT` (+40, guarded by `hist.amount is not None`) · date within `DUP_DATE_WINDOW_DAYS` (+20) · invoice# `JaroWinkler.similarity ≥ DUP_INVOICE_JW_THRESHOLD` (+20) · line fingerprint `token_set_ratio ≥ DUP_LINE_ITEMS_THRESHOLD` (+20). Best score `≥ DUP_FUZZY_HOLD_SCORE` → **`HOLD_DUP_FUZZY`**. `values`: `matched_invoice, score, amount, prior_amount`.

## `vendors.py` — approved-vendor gate, fuzzy name match, bank-change
**`check(extract, vendors) -> (list[Reason], matched Vendor|None)`** (+ `name_score`, `match_vendor`).
- **`name_score`** = mean of `token_set_ratio` and `JaroWinkler×100`, best over the vendor's `normalized_name` and `legal_name` (0–100).
- Best match `is None` or `score < VENDOR_MATCH_FLOOR` (80) → **`HOLD_VENDOR_UNAPPROVED`** (ghost/unapproved); returns matched vendor `None`. `values`: `vendor_name, score`.
- At/above floor: if `not approved` → **`HOLD_VENDOR_UNAPPROVED`** (rule `approved-vendor gate`); elif `score < VENDOR_MATCH_AUTO` (92) → **`HOLD_VENDOR_FUZZY`** (80–92 confirm band); else → **`OK_MATCH`** (INFO, rule mentions "vendor").
- **Bank-change (independent):** `extract.remit_to_bank` present, vendor has `bank_account_hash`, and they differ → **`HOLD_BANK_CHANGE`**. `values`: `vendor_id, remit_to_bank, on_file`. (decide() also emits a `fraud_flag` notification.)

## `coding.py` — GL account + cost-centre prediction
**`predict(extract, vendor, historical=None) -> (GLCoding, list[Reason])`**.
- `account`/`cost_center` taken from the vendor master defaults. Confidence: both → `CODING_CONF_FULL` (0.95); one → `CODING_CONF_PARTIAL` (0.55); neither → `CODING_CONF_NONE` (0.20).
- `confidence < CODING_CONFIDENCE_GATE` (0.80) → **`HOLD_CODING_LOW_CONF`** ("needs manual coding"). `values`: `account, cost_center, confidence`. The `GLCoding` is always returned (feeds overall confidence + the CODED stage).

## `anomaly.py` — spend burst vs vendor history
**`check(extract, historical) -> list[Reason]`**.
- Amount = `total` (fallback subtotal). Needs `len(amounts) ≥ ANOMALY_MIN_HISTORY` (2) or returns `[]`.
- `mean = avg(history)`, `hi = max(history)`. Flags if `amount > ANOMALY_MEAN_MULTIPLIER × mean` **OR** `amount > ANOMALY_MAX_MULTIPLIER × hi` → **`HOLD_ANOMALY`**. `values`: `amount, mean, max, x_mean, x_max, n`.
- decide() passes it **only same-vendor** history, and `[]` for an unmatched vendor (no false burst).

## `policy.py` — everything that isn't one artifact check
All pure; `po_bypass` also returns `Notifications`.

| Function | Signature | Rule / threshold | Emits (`values` keys) |
|----------|-----------|------------------|-----------------------|
| `document_type` | `(extract) -> list[Reason]` | `doc_type` in {STATEMENT, OTHER} | **`REJECT_NOT_INVOICE`** (`doc_type`) |
| `missing_critical` | `(extract) -> list[Reason]` | any of `vendor_name, invoice_number, invoice_date, total` null/blank (`CRITICAL_FIELDS`) | **`REJECT_MISSING_CRITICAL`** (`missing`) |
| `po_status` | `(po) -> list[Reason]` | `po.status` in {closed, expired} | **`REJECT_PO_EXPIRED`** (`po_number, status`) |
| `credit_memo` | `(extract) -> list[Reason]` | `doc_type==CREDIT_MEMO` or `total < 0` | **`HOLD_CREDIT_MEMO`** (`doc_type, total`) — also causes decide() to skip financial gates |
| `confidence_gate` | `(extract) -> list[Reason]` | any `validation[k] is False` (arithmetic) → HOLD; else any per-field `confidence[k] < CONFIDENCE_GATE`, **ignoring keys starting `_`** | **`HOLD_LOW_CONFIDENCE`** (`failed` or `low_fields, gate`) |
| `currency` | `(extract, po) -> list[Reason]` | PO present and `extract.currency != po.currency` | **`HOLD_CURRENCY`** (`invoice_currency, po_currency`) |
| `po_bypass` | `(extract, vendor, po) -> (list[Reason], list[Notification])` | Only when **no PO**. amount `≥ PO_BYPASS_LIMIT` → REJECT; else approved + `po_bypass_allowed` → OK + notify; else HOLD | **`REJECT_NO_PO_OVER_BYPASS`** / **`OK_BYPASS`** (+ `bypass_notice`) / **`HOLD_MATERIALITY`** (`amount, limit, vendor_id`) |
| `split_threshold` | `(extract, historical) -> list[Reason]` | amount < `SPLIT_THRESHOLD`, ≥2 siblings each < limit within `SPLIT_WINDOW_DAYS`, sum ≥ limit | **`HOLD_SPLIT_THRESHOLD`** (`count, sum, limit`) |
| `materiality_band` | `(amount) -> str` | DOA bands | `"<5k" / "5k-25k" / "25k-100k" / ">100k"` |
| `route_for` | `(amount) -> str` | DOA bands | `"manager" / "director" / "VP" / "CFO"` |

> `HOLD_TAX` exists in the `ReasonCode` enum but no gate currently emits it (reserved; a tax-sanity check was scoped out). `validate.py` does a tax-rate plausibility check that lowers confidence, but does not raise `HOLD_TAX`.

## `decide.py` — orchestration (detailed in `03_DECISION_LOGIC.md`)
`decide(extract, vendors, po, goods_receipt, historical_invoices) -> DecisionResult`. Runs the gates in a fixed
order, collects all `Reason`s, applies `_precedence`, computes `_overall_confidence`, materiality band, DOA
routing, GL coding, matched PO, cumulative-after, and notifications. Helpers: `_amount` (total→subtotal),
`_overall_confidence` (min of extraction-conf and coding-conf), `_precedence`, `_run_vendor` (lazy import to
avoid the `vendors` param shadowing the module).
