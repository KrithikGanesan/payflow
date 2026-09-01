# Demo Narration — speak the mechanism, not the screen

**The fix for "I'm just reading what's on screen":** at each stage say three things —
(1) what the system is *deciding*, (2) the two *numbers* it compares, (3) *why it matters*.
Formula: *"Here it's [deciding X] — [number] vs [number] — [so what]."*
Lead each case with the ONE insight; end each stage on the judgment, not the label.

---

## CASE 1 — Acme $12,000 → APPROVE  (clean 3-way, the baseline)
**Lead line:** *"This is the 80% we want to auto-clear — but watch how many independent checks it still passes before we trust it."*

| Stage | Mechanism + numbers | SAY THIS |
|-------|---------------------|----------|
| Received | PDF ingested, hashed (sha256). The hash is our cache + dedupe key. | "First we fingerprint the file — that hash is how we cache extraction and catch duplicates later." |
| Extracted | Gemini reads image **+** text layer → vendor *Acme Corporation Inc.*, PO-1001, $12,000, line items. Then arithmetic check: line items ($12,000) = subtotal; subtotal + $0 tax = total. Per-field confidence ~0.97. | "The model reads the layout and the text, and I don't just trust it — I check the math reconciles: line items sum to the subtotal, subtotal plus tax equals the total. It does." |
| Coded | Predicts GL account **5010**, cost centre **CC-300** from this vendor's history/defaults. Confidence **0.95 ≥ 0.80** gate → pass. | "This is the part real AP actually spends its day on — which budget does it hit. We predict the GL account and cost centre, and only auto-clear if we're confident. 95%, so we proceed." |
| Matched | 3-way: PO-1001 requires a goods receipt. GR-9001 recorded **$12,000** received. Billed **$12,000 ≤ received $12,000**; cumulative **$12,000 ≤ PO $12,000**. | "This is a 3-way match, not two-way — invoice equals the PO **and** equals what was physically received. We confirm the goods actually landed before we pay." |
| Validated | Tolerance: $12,000 vs $12,000 = **0%** (within ±1%/$25). Duplicates: none. Vendor: approved, name **100%**, bank matches. Anomaly: $12k vs history mean ~$12k — normal. Currency: USD=USD. Confidence gate: pass. | "Now every risk gate runs at once — tolerance, duplicate, vendor identity, spend anomaly, currency, confidence. All green." |
| Decided | No HOLD/REJECT reason → precedence → **APPROVE**. $12k sits in the $5k–25k DOA band → would route to a Director if a human were needed. | "Nothing flagged, so it's straight-through approve. And notice — if it *had* needed a human, it already knows this dollar size routes to a director." |

---

## CASE 2 — Stark $10,300 goods (+$800 tax = $11,100 total) → HOLD  (the explainability money-shot)
**Lead line:** *"The total on this invoice is $11,100, but I'm not going to compare that to the PO — watch why."*

| Stage | Mechanism + numbers | SAY THIS |
|-------|---------------------|----------|
| Extracted | Subtotal **$10,300**, tax **$800**, total **$11,100**, PO-1004. Arithmetic reconciles. | "It reads a $10,300 goods subtotal, $800 tax, $11,100 total — and the math checks out, so this isn't an extraction error. The variance is real." |
| Coded | GL from Stark's defaults, confident → pass. | "Coding's fine — not where the problem is." |
| Matched | PO-1004 authorises **$10,000**. Cumulative if we pay: **$10,300 > $10,000 + 1% cap ($10,100)** → **HOLD_OVERBILL**. | "The PO authorised ten thousand. This bills ten-three. Paying it means paying more than the PO allows — the over-billing guard stops it." |
| Validated | Tolerance compares the **goods subtotal $10,300 vs PO $10,000 = +3.0%**, past the ±1%/$25 band → **HOLD_TOLERANCE**. The **$800 tax and $11,100 total are excluded** from this comparison. | "Here's the judgment: I compare the *goods* — $10,300 — to the $10,000 PO. That's 3% over, past tolerance, so hold. The $800 tax is legitimate, not a discrepancy, so I deliberately leave it out. A naive matcher compares the $11,100 total to the PO and either wrongly rejects, or misses that the goods themselves are over." |
| Decided | Most-severe reason is HOLD → **HOLD**, routed to a human (Director band). The reason literally reads: *subtotal $10,300 vs PO $10,000 = +3.0%, over ±1%/$25; tax/freight excluded.* | "So — HOLD, routed to a director, and the reason cites the exact two numbers and the rule. The clerk resolves this in seconds because we told them precisely what and why." |

---

## CASE 3 — Hooli $10,000 → APPROVE  (multi-GR: the real-3-way signature)
**Lead line:** *"This PO was delivered in two shipments — and that's exactly where naive matchers break."*

| Stage | Mechanism + numbers | SAY THIS |
|-------|---------------------|----------|
| Extracted | Vendor *Hooli Cloud Services*, PO-1013, total **$10,000**. | "Standard-looking $10,000 invoice against PO-1013." |
| Coded | GL 5010 / CC-200, confident → pass. | "Coding clean." |
| Matched | PO-1013 was received in **two** goods receipts: GR-9013a **$4,000** + GR-9013b **$6,000**. The engine **sums them → $10,000**. Billed **$10,000 ≤ received $10,000** → match. | "The goods came in two deliveries — four thousand, then six. A naive 3-way match checks the invoice against the *first* receipt, sees $10,000 against $4,000, and wrongly flags an over-bill. We **sum all receipts** — four plus six is ten — and it matches cleanly. That's what three-way matching actually means in the real world." |
| Validated | Tolerance 0%; no duplicate; vendor approved; **no history → anomaly gate skipped**; currency USD. | "All gates green — and note the anomaly check simply skips because this is a new vendor with no baseline yet, rather than firing a false alarm." |
| Decided | No flags → **APPROVE**. | "Clean approve — but only because we understood the receipts, not despite it." |

---

## If they push (quick answers)
- **"Why HOLD not reject on Stark?"** — A wrong auto-approve loses real money; a hold costs a clerk two minutes. Over-tolerance is *probably* wrong but might be a legit price update — so a human decides. I reserve REJECT for the unambiguous (exact duplicate, expired PO).
- **"How do you know the tax is legit and not padding?"** — I don't blindly trust it; the tax rate has a plausibility band, and the arithmetic must reconcile (subtotal+tax=total). If either fails, confidence drops and it holds.
- **"What if two shipments over-deliver?"** — The summed receipts still can't exceed the PO by more than tolerance; the same over-billing guard applies to the aggregate.
- **"Is this just Gemini?"** — Gemini only *extracts*. Every decision is a separate, pure, tested rules engine — 70 tests — so the judgment is deterministic and auditable, not a model guess.
