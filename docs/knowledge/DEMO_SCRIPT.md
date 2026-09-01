# Verdict — Demo Script & Interview Talking Points

_≤5-min video: happy path + ≥1 edge case, narrated, no slides. Then a live interview demo. Have runs rehearsed and in order._

## Setup (before recording)
- `backend/.env` has `GEMINI_API_KEY`; run each demo invoice **once live** first so results cache (deterministic replay — no flaky call mid-demo). Or set `EXTRACTION_PROVIDER=fixture` for guaranteed-instant.
- Click the **"seed demo data"** action so the Dashboard is populated with history.
- `./demo` running; browser on the **Live Run** screen.

## Running order (each ~30–45s)
| # | Invoice | Verdict | One-line narration |
|---|---------|---------|--------------------|
| 1 | Clean happy-path | ✅ APPROVE | "Matched the PO, within tolerance, GL-coded automatically — straight through in seconds." |
| 2 | Tax-over-tolerance | ⏸️ HOLD | "It didn't just reject the mismatch — it reconciled subtotal vs PO and saw the extra $300 is *freight*, then flagged it for a human." |
| 3 | Split-PO partial | ✅ APPROVE | "This vendor bills in installments. It tracks *cumulative* billed against the PO — approves because we're still under the total." |
| 4 | Fuzzy duplicate | ⏸️ HOLD | "Different invoice number, but same vendor/amount/date/lines as one we've seen. Held with the twin shown — and I hold, not reject, so a legit re-bill isn't blocked." |
| 5 | Scanned / low-confidence | ⏸️ HOLD | "Blurry scan — confidence on the total is low, so it refuses to guess-approve and routes the flagged fields to review." |
| 6 | PO-bypass small + notify | ✅ APPROVE | "Under $500 from an approved vendor, no PO needed — auto-approved, *but* it fires a notice to finance so nothing happens silently." |
| — | Close on **Dashboard** | — | "Across these runs: X% straight-through, here's the exception breakdown and spend by vendor." |

_Optional extras if time: spend anomaly (20× usual → HOLD), unapproved/name-mismatch vendor, credit memo, bank-detail-change flag._

## The narration that wins (say these)
- **Explainability:** every verdict cites the *values compared* and the *rule*, in plain English — a non-technical AP clerk can act on it in 20 seconds.
- **The GL-coding insight:** "Real AP teams don't spend the day catching fraud — they spend it deciding which budget each bill hits. That's GL coding, the #1 reason invoices go to a human, so I built it in."
- **Asymmetric-risk philosophy:** "A wrong auto-approve loses real money; an extra hold costs two minutes. So the system is deliberately conservative — when unsure, it holds."
- **Confidence × Materiality:** "Scrutiny scales with both how sure the AI is and how much money is at stake."
- **Precedence:** "One red flag beats ten green checkmarks — a clean invoice from an unapproved vendor still holds."
- **Deliberate scope (maturity):** "I scoped out sanctions screening, 1099 tracking, and month-end accruals on purpose — here's exactly where they'd plug in." (Shows you see the whole board.)
- **Trust/security:** during research, an AWS doc tried a prompt-injection to run shell commands — the agent ignored it. Nice aside on building trustworthy automation.
- **Reliability:** "Extraction is cached per file — it ran for real, and it replays deterministically so a demo never dies on a slow API call."

## If something breaks live
Fall back to `EXTRACTION_PROVIDER=fixture` (ground-truth JSON, instant) and keep narrating the decision logic — the engine is what's graded, and it's pure + fully tested.

---

## ⭐ Recommended 5-minute run (current — includes the two 3-way cases)

Case study asks for 2–4 edge cases; show **happy path + 3 edges**, each a different kind of judgment. Rehearse this order:

| Time | Run | Screen | Result | One line |
|------|-----|--------|--------|----------|
| 0:00 | Hook — the problem | — | — | "Invoice in → a decision you can defend, every step visible." |
| 0:30 | Upload **Acme $12k** (fresh) | Live Run | APPROVE | "Never seen it — read live, 3-way matched, straight through." |
| 1:15 | Upload **Hooli $10k** | Live Run | APPROVE | "Received in **two shipments** — engine **sums the receipts**; a naive matcher rejects against the first." |
| 2:05 | **Stark $10,300** | Decision Flow | HOLD | "Matching & Tolerance drove it — goods 3% over PO; it **ignored the $800 tax**." |
| 3:05 | **Cyberdyne $40k** | Live Run | HOLD | "Matches the PO exactly — but **20× the vendor's normal**. Held like a fraud alert." |
| 3:50 | *(opt)* **Pied Piper $8k** | Live Run | HOLD | "Invoice beat the goods — **hold awaiting receipt, not reject**." |
| 4:25 | Dashboard close | Dashboard | — | "STP rate + why the rest held; and here's what I scoped out on purpose." |

**Lead the story on multi-GR (Hooli)** — the deepest 3-way signal — paired with Stark for explainability.
If over time: cut Pied Piper (happy + 3); if tight: happy + Hooli + Stark only.
Prove live once (Acme upload); narrate through the Gemini spinner; warm-up call + backup before recording.
