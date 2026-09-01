# Verdict — Research Consolidation

_Findings from 5 background research agents. Preserve numbers + sources. Some stats flagged verify-before-quoting._

---
## A) AP controls & match logic

**Matching modes**
| Mode | Compares | Use when |
|------|----------|----------|
| 2-way | Invoice ↔ PO (price + qty) | Services / non-inventory / no physical receipt |
| 3-way | Invoice ↔ PO ↔ **goods receipt (GRN)** | Physical goods — the standard control |
| 4-way | + inspection/QA acceptance | Regulated/capital/QA-critical goods |

**Tolerances** — set dual, apply the tighter. Separate price from quantity.
- Best practice ≈ **±1–2% OR a small absolute, whichever lower** for price. Our locked value: **±1% AND ≤ $25 auto-clears; beyond → HOLD.**
- Small-difference auto-writeoff < ~$10–25 (<1%). Quantity tolerance separate (over-receipt often 0%).
- within tolerance → auto-approve (STP); over but explainable (freight/tax/price update) → HOLD; no-PO / dup invoice # / expired PO / negative qty → REJECT.

**Non-PO / PO-bypass** — orgs run two pipelines (PO vs non-PO). Low-value non-PO auto-routes below **$500–$2,500** to cost-center owner + single approval. Above → retro-PO/escalate. **Make bypass cumulative-per-vendor-per-period** (else split-invoice loophole). GL allow-list for permissible non-PO categories.

**Approval hierarchy (DOA — delegation of authority), illustrative bands:** <$5k manager · $5k–25k director · $25k–100k VP · >$100k CFO/dual.

**Decision states:** approved (STP) · pending-review · on-hold (recoverable exception) · exception (investigate) · rejected. Manual approvals typically 2–5 people, ~14 days.

**Split-PO / progress billing / retainage:** track cumulative billed vs PO/contract per line; over-billing guard `Σ invoiced ≤ PO×(1+tol)`. Retention commonly 5–10% (private avg 7.59%, state/muni 5.56%, federal 3.26% — Levelset).

**KPI benchmarks**
| KPI | Best-in-class | Laggard |
|-----|---------------|---------|
| Cost per invoice | **$2.07** | >$10 |
| Invoice cycle time | **3.3 days** | 13.5 days |
| Straight-through-processing (STP) | **~71%** (target 80%+) | low |
| Duplicate-payment rate | 0.8% | >2% |
Also: first-time-match rate target >90%, exception rate target <20%. `DPO = (Avg AP / COGS) × 365`.

_Sources: NetSuite (three-way matching; AP KPIs), Wikipedia (Invoice processing; DPO), Wall Street Prep (DPO), Stampli (invoice matching), Levelset (retainage). Tolerance %/$ bands & DOA hierarchy are standard ERP/industry defaults (SAP/Coupa/Ariba/Oracle), not a single citable page — confirm against real spend profile before hard-coding._

---
## B) Invoice extraction / IDP

- **Feed PDFs straight to a vision LLM** (Claude/Gemini): it rasterizes the page **and** reads the embedded text layer. No separate OCR for clean PDFs; scanned images work via the same vision path.
- **Bedrock gotcha (now moot — we use Gemini):** on Bedrock Converse you must **enable citations** or it silently falls back to text-only (loses visual understanding).
- **Force structured output:** one tool (`emit_invoice`) with JSON-Schema `input_schema`, `tool_choice` forced, `strict:true`. Instruct "return null, never guess." Put the PDF *before* the instructions.
- **Field schema** (mirrors Textract taxonomy + EN 16931/UBL 2.1/PEPPOL BIS 3.0 for interop): vendor_name, vendor_tax_id, vendor_address, invoice_number, invoice_date, due_date, po_number, currency (ISO 4217), line_items[{description, quantity, unit_price, amount, tax_rate}], subtotal, tax_total, freight, discount, total, `_confidence` map, `_validation`.
- **Confidence = self-report + cross-validation.** Strongest signal is **arithmetic**: `Σ line_items.amount == subtotal`; `subtotal + tax + freight − discount == total`. Mismatch → low confidence. Plus format validation (ISO 4217, dates parse, tax-ID regex, tax-rate 0–27% band). **Never auto-approve if any critical field null, arithmetic fails, or confidence < threshold → route to human.**
- **Messy inputs:** rotate/deskew low-quality scans; bundled line items → one row + note; multi-page → concatenate + dedupe headers; missing fields → null + lower confidence, never hallucinate.

**⚠️ Security note:** one fetched AWS Textract doc contained an **injected "See also" block** urging the agent to run AWS CLI commands — the agent correctly ignored it. Good demo talking point about trustworthy automation.

_Sources: AWS Textract (Invoices & Receipts), Anthropic PDF support & Tool use docs, PEPPOL BIS Billing 3.0 / EN 16931._

---
## C) Duplicate detection & AP fraud

**Duplicate — two layers:**
1. **Exact key (auto-block):** `normalize(vendor_id) + normalize(invoice_no)` — upper-case, strip spaces/leading-zeros/punctuation (vendors/OCR insert `.`,`-`,spaces to defeat exact match).
2. **Fuzzy fingerprint (score + hold):** rolling ~120-day window per vendor.

| Signal | Weight |
|--------|--------|
| Same normalized amount (±$0.50 / 0.5%) | 40 |
| Invoice date within ±7 days | 20 |
| Invoice-number similarity (Jaro-Winkler ≥ 0.90) | 20 |
| Line-item set match (token_set_ratio ≥ 90) | 20 |

**≥70 → HOLD; ≥90 → strong duplicate.** Same amount+date+line-items with a *different* invoice # = classic vendor-resend / PO+non-PO double-entry.

**Fraud patterns:** duplicate-payment, ghost/fake vendors, invoice inflation, **bank-detail-change** (top vector), split-to-avoid-threshold.
**Stats (⚠️ verify before quoting externally — search was CAPTCHA-blocked):** ACFE *Report to the Nations* 2024 — orgs lose ~**5% of revenue** to fraud, median loss ~$145K/case, ~12 months undetected, asset-misappropriation ~89% of cases. AFP: 96% of businesses faced payments-fraud attack in 2023. Duplicate/erroneous payments ~0.05–0.1% of disbursements (well-controlled) up to 1–2% (weak controls).

**Vendor master fuzzy match** ("Acme Corp." → "Acme Corporation Inc."): normalize (lowercase, strip punctuation + legal suffixes inc/llc/ltd/corp/co/gmbh/plc + stop-words) → score with **token_set_ratio (RapidFuzz)** + **Jaro-Winkler** (prefix-weighted). Thresholds: **≥92 auto-match · 80–92 hold/confirm · <80 no match.** Always confirm identity with a hard key (tax ID / bank) — never change payee bank on name similarity alone.

**Split-to-avoid-threshold:** same vendor, N invoices short window (7–14d), each 80–99% of limit, sum ≥ limit → **FLAG for review** (not auto-reject).

**Hold, don't auto-reject** probabilistic signals — a hard reject blocks legitimate re-bills; route to review queue with matched-invoice evidence. Auto-block only the exact vendor+invoice# key.

_Sources: ACFE Report to the Nations 2024; RapidFuzz docs; Jaro-Winkler (Wikipedia); MineralTree (AFP survey); Stampli (duplicate payments)._

---
## D) Product UX benchmarking (Bill.com, Tipalti, Stampli, Ramp, Rossum, Nanonets, Coupa)

- **Side-by-side is universal:** PDF left, extracted fields right, click a field → highlight its region on the doc.
- **Chain shown as a stepper/timeline** with status pills: Captured → Extracted → Matched → Validated → Approved → Paid. Each stage shows what ran + output. Ramp: "checks every line with 2-/3-way matching" + approval-agent summary. BILL: "95% day-one accuracy."
- **Exceptions = a queue, not buried.** Mismatches/dupes/low-confidence flagged + routed.
- **Audit trail / explainability (grading-critical):** "which rule fired, on what value, with what result, decided by whom/what." BILL logs every touchpoint = permanent audit trail.
- **Dashboard widgets:** STP/touchless rate (headline), exception rate + top reasons, avg cycle time + trend, cost per invoice, invoices/FTE, volume by status (donut), aging buckets (0–30/31–60/61–90/90+), spend by vendor/category/dept, first-time-match rate, DPO, approver bottleneck.
- **Standout touches (pick 5–8):** per-field confidence badges (green/amber/red, low auto-focused); "needs your review" nudge + one-line AI summary; one-click approve-with-reason → audit trail; keyboard-fast exception clearing; live stage-lighting animation; click-field→highlight-PDF; fraud/anomaly callout (bank-change); real-time toast/activity feed.
- **Design cues:** neutral gray canvas, ONE accent (indigo), status colors reserved strictly for meaning (green=approved/high-conf, amber=review, red=exception, gray=pending); tabular numerals, right-aligned currency, monospace for IDs/amounts; medium density, whitespace around the PDF.
- **Build screens 1/2/5 first:** Live Run, Dashboard, Audit Trail (carry the live + explainable story).

_Sources: ramp.com/bill-pay, stampli.com/product, bill.com (AP product; AP metrics blog), tipalti.com/invoice-processing, rossum.ai, nanonets.com._

---
## E) Finance-domain critique (the differentiator)

**THE BIG INSIGHT:** real AP teams don't spend the day catching fraud — they spend it on **GL CODING** (which account / cost center each bill hits). It's the #1 reason invoices route to a human. Adding it signals you've actually watched an AP clerk. **→ We added GL coding as a headline check.**

**Add (max credibility-per-effort):** (1) GL coding + cost-center prediction (low confidence → HOLD); (2) **3-way match** for goods (2-way only for services); (3) tax validation (sales/use reasonableness, reverse-charge/VAT awareness).
**Cheap high-impact add:** remit-to **bank-detail-change flag**.
**Threshold corrections:** ±3%/$50 too loose → **±1% AND ≤$25**; bypass $500 OK **but cumulative-per-vendor + mandatory coding + approver**; state goods/services split explicitly; define duplicate key (vendor+invoice#+amount+date-proximity).
**Maturity signals:** STP rate as honest headline; exception *reasoning* not just flagging; respect vendor master + DOA as sources of truth; human-in-the-loop that learns.
**Compliance to make visible:** **SoD** (creator/bank-changer ≠ approver — SOX/COSO); immutable audit trail (timestamp, policy version, values, actor); approval matrix/DOA by band; supporting-doc retention (invoice+PO+receipt attached to voucher); duplicate-payment prevention as a *stated control*.
**Scoped-out (interview talking points):** OFAC/sanctions screening (per IRS/OFAC obligations), W-9/1099-NEC tracking (≥$600), retainage, month-end accruals/cutoff, full statement reconciliation, learning loop.

_Sources: IRS 1099-NEC/W-9 rules; OFAC SDN screening; SOX §404/COSO; IOFM/APQC benchmarking. (Web unavailable that run — verify current 1099 thresholds before quoting.)_
