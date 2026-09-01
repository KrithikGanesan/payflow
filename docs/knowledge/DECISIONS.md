# Verdict — Locked Design Decisions

_The design the user approved ("lock it" / "let's gooo"). Change only with explicit user sign-off._

## The decision philosophy (the spine — 4 principles)
1. **Asymmetric risk → bias to HOLD.** A wrong auto-approve loses real, hard-to-recover money; an unnecessary hold costs ~2 min of a clerk's time. When uncertain: **HOLD**. **REJECT** only when unambiguously wrong.
2. **Scrutiny scales with Confidence × Materiality.** Extraction confidence AND dollar amount both decide how much human attention an invoice gets. A $40 / 85%-conf invoice → approve; a $400k / 99%-conf invoice → still routes to senior sign-off.
3. **Precedence — most-severe outcome wins.** Gates are ordered; one failed gate downgrades the whole decision. A clean invoice from an unapproved vendor still HOLDs.
4. **Every decision cites policy + values.** e.g. *"HOLD · total $10,300 vs PO $10,000 = +3.0%, over ±1% tolerance; variance = $300 freight not on PO."* This is what's graded hardest.

**Goal metric:** maximize **STP rate** while catching 100% of risky items. The product hands the clerk a pre-investigated exception, it doesn't replace them.

## Thresholds (locked values — in `backend/app/engine/config.py`)
| Control | Value |
|---------|-------|
| Price/total tolerance | **±1% AND ≤ $25** auto-clears; beyond → HOLD (quantity tolerance separate) |
| PO-bypass | **< $500**, approved vendor, bypass category → APPROVE **+ notify finance**; cumulative-per-vendor cap *(designed, NOT implemented in code)*; still coded + approver |
| Duplicate — exact | vendor + normalized invoice# + amount + date-proximity → **REJECT** |
| Duplicate — fuzzy | weighted score (amount 40 / date±7d 20 / invoice-no JaroWinkler≥0.90 → 20 / line-items token_set≥90 → 20); **≥70 → HOLD** |
| Vendor name match | token_set_ratio + Jaro-Winkler; **≥92 auto · 80–92 HOLD · <80 HOLD** (possible ghost vendor) |
| Confidence gate | any critical field null, arithmetic fails, or conf **< 0.80** → HOLD |
| Spend anomaly | > ~5× vendor mean or > 2× vendor max → HOLD |
| Match mode | **2-way services / 3-way goods** (PO.requires_goods_receipt) |
| DOA bands (routing) | <$5k manager · $5k–25k director · $25k–100k VP · >$100k CFO/dual |

## Decision states & precedence (most-severe wins)
- **REJECT (hard block):** exact duplicate · PO expired/closed · missing critical field · not an invoice
- **HOLD (fraud/compliance):** unapproved/ghost vendor · bank-detail change · split-to-avoid-threshold
- **HOLD (financial):** over tolerance · over-billing · low confidence · low-confidence GL coding · anomaly · credit memo · currency mismatch
- **APPROVE:** clean match, or PO-bypass under threshold (+ notify)
- **SoD (hard rule):** the actor that creates a vendor / changes bank detail can never also approve payment. *(designed; NOT enforced in code — interview talking point)*

## The checks — three tiers
**BUILD (demo runs on these):** extraction + confidence gate · 2-way/3-way match · tolerance (±1%/≤$25) · **GL coding** · duplicate (exact+fuzzy) · approved-vendor + fuzzy-name match · PO-bypass + finance notice · split-PO cumulative billing · **spend anomaly** · credit-memo · decision engine w/ precedence + DOA routing · immutable audit trail.

**BUILD IF TIME:** bank-detail-change flag · tax sanity check · early-payment-discount reminder (value-add, not a gate) · split-to-avoid-threshold flag · document-type gate.

**DESIGNED, SCOPED OUT (interview talking points):** OFAC/sanctions · W-9/1099 · retainage · month-end accruals · full statement reconciliation · learning-from-corrections loop.

## The 6 featured demo edge cases (each = a different kind of judgment)
| # | Edge case | Shows |
|---|-----------|-------|
| 1 | Split-PO / partial billing | **Stateful** reasoning (cumulative billed vs PO) — most impressive |
| 2 | Fuzzy duplicate | Fraud awareness + "why HOLD not REJECT" |
| 3 | Tax-over-tolerance | Financial nuance: total ≠ mismatch (reconcile subtotal, tax/freight separate) |
| 4 | Scanned / low confidence | Graceful degradation, confidence-aware |
| 5 | PO-bypass under threshold + notify | Policy logic — auto-approve **but nothing silent** (user's explicit ask) |
| 6 | Spend anomaly | Fraud instinct — "20× this vendor's usual → HOLD" (user's explicit ask) |

## Why these tech choices
- **Gemini free tier over Bedrock/OpenAI/Ollama:** Bedrock access lost (SSO expired / no model access); the user wanted a personal, zero-cost key (not a work cloud account). New ChatGPT/Claude *API* keys aren't truly free (need billing). Gemini AI Studio has a genuine free tier + strong document vision. Ollama kept as a "runs 100% local, no key" alternative.
- **Provider-agnostic extraction + fixture mode + caching:** demo reliability. Extraction cached by sha256(pdf) → first run live, re-runs instant & deterministic → a slow/flaky API call can never kill the live demo, but it still genuinely ran. `fixture` provider runs the whole app with no key.
- **Decision engine = pure functions + TDD:** the defensible core; each edge case is a test.

## Things the user explicitly asked for
- All **6+ edge cases** (didn't want to trim to 4).
- **Spend anomaly** detection (their idea — sudden burst vs history → HOLD).
- **PO-bypass fires a finance-owner notification** (auto-approve but not silent).
- **Plain-English / "dumb it down" explanations** — the user wanted the AP domain explained simply (see the glossary in chat: PO, matching, tolerance, duplicate, approved vendor, bypass, split billing, confidence).
- Knowledge/handoff docs written by a **subagent**, not inline, so nothing is lost on compaction.
- Parallel subagents for research and for the build.
