"""Named thresholds for the Verdict decision engine.

Single source of truth for every tunable number. No logic here — pure constants
so the rules that reference them stay auditable and the values are testable.
Rationale for each choice lives in the design spec (§4 checks, §5 precedence).
"""
from __future__ import annotations

# ── price / total tolerance ─────────────────────────────────────────
# Auto-clear a PO-to-invoice variance only if it is within BOTH bounds
# (i.e. the *tighter* of ±1% or $25). Beyond the tighter bound → HOLD.
TOLERANCE_PCT: float = 0.01          # ±1%
TOLERANCE_ABS: float = 25.0          # ≤ $25

# ── PO-bypass (no-PO auto-approve) ──────────────────────────────────
PO_BYPASS_LIMIT: float = 500.0       # strictly under $500, approved + bypass vendor

# ── duplicate detection ─────────────────────────────────────────────
DUP_WEIGHT_AMOUNT: int = 40          # amount matches (within DUP_AMOUNT_PCT)
DUP_WEIGHT_DATE: int = 20            # invoice_date within ±DUP_DATE_WINDOW_DAYS
DUP_WEIGHT_INVOICE_NO: int = 20      # invoice-number Jaro-Winkler ≥ threshold
DUP_WEIGHT_LINE_ITEMS: int = 20      # line-item token_set_ratio ≥ threshold

DUP_AMOUNT_PCT: float = 0.01         # amount considered equal within ±1%
DUP_DATE_WINDOW_DAYS: int = 7        # ± days that count as "same period"
DUP_INVOICE_JW_THRESHOLD: float = 0.90
DUP_LINE_ITEMS_THRESHOLD: int = 90   # token_set_ratio 0..100
DUP_FUZZY_HOLD_SCORE: int = 70       # total weighted score ≥ 70 → HOLD_DUP_FUZZY

# Exact-duplicate key: same vendor + normalized invoice# + amount + near date.
DUP_EXACT_AMOUNT_ABS: float = 0.01   # amounts equal to the cent
DUP_EXACT_DATE_WINDOW_DAYS: int = 7  # resubmission within a week is "the same one"

# ── approved-vendor / fuzzy name match ──────────────────────────────
VENDOR_MATCH_AUTO: float = 92.0      # ≥ 92 → confident auto match
VENDOR_MATCH_FLOOR: float = 80.0     # 80–92 → HOLD for review; < 80 → no match (HOLD unapproved)

# ── extraction confidence gate ──────────────────────────────────────
CONFIDENCE_GATE: float = 0.80        # any critical field below → never auto-approve

# ── GL coding confidence gate ───────────────────────────────────────
CODING_CONFIDENCE_GATE: float = 0.80
CODING_CONF_FULL: float = 0.95       # vendor supplies both account + cost centre
CODING_CONF_PARTIAL: float = 0.55    # only one of the two known
CODING_CONF_NONE: float = 0.20       # nothing to go on

# ── spend anomaly (vs vendor history) ───────────────────────────────
ANOMALY_MEAN_MULTIPLIER: float = 5.0   # > 5× vendor mean → burst
ANOMALY_MAX_MULTIPLIER: float = 2.0    # > 2× vendor historical max → burst
ANOMALY_MIN_HISTORY: int = 2           # need a baseline before flagging

# ── split-to-avoid-threshold ────────────────────────────────────────
SPLIT_WINDOW_DAYS: int = 14            # sibling invoices within this window
SPLIT_THRESHOLD: float = 5000.0        # the approval limit being dodged (manager band)

# ── delegation of authority (DOA) routing bands ─────────────────────
DOA_MANAGER: float = 5000.0          # < $5k  → manager
DOA_DIRECTOR: float = 25000.0        # $5k–25k → director
DOA_VP: float = 100000.0             # $25k–100k → VP ; > $100k → CFO
