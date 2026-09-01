"""Duplicate-invoice detection.

- Exact key: same vendor + normalized invoice# + amount (to the cent) + near date
  → REJECT_DUP_EXACT (a true re-post of a paid/queued invoice).
- Fuzzy fingerprint (rapidfuzz): weighted score over amount / date / invoice-no
  (Jaro-Winkler) / line-items (token_set_ratio). ≥ 70 → HOLD_DUP_FUZZY, citing the
  matched prior invoice — a probable resubmission that a human should eyeball.

Pure: (InvoiceExtract, list[HistoricalInvoice], vendor_id) -> list[Reason].
"""
from __future__ import annotations

import re
from datetime import date

from rapidfuzz.distance import JaroWinkler
from rapidfuzz.fuzz import token_set_ratio

from app.contracts import HistoricalInvoice, InvoiceExtract, Reason, ReasonCode, Severity
from . import config

_RULE_EXACT = "exact key: vendor + invoice# + amount + date±7d"
_RULE_FUZZY = "fuzzy fingerprint ≥ 70 (amount 40 / date 20 / invoice# 20 / lines 20)"


def normalize_invoice_no(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _days_apart(a: str | None, b: str | None) -> int | None:
    da, db = _parse_date(a), _parse_date(b)
    if da is None or db is None:
        return None
    return abs((da - db).days)


def _line_fingerprint(extract: InvoiceExtract) -> str:
    return " ".join((li.description or "").strip() for li in extract.line_items).strip().lower()


def _fuzzy_score(extract: InvoiceExtract, amount: float, hist: HistoricalInvoice) -> int:
    score = 0
    # amount
    if hist.amount is not None and abs(amount - hist.amount) <= abs(hist.amount) * config.DUP_AMOUNT_PCT + 1e-9:
        score += config.DUP_WEIGHT_AMOUNT
    # date proximity
    dd = _days_apart(extract.invoice_date, hist.invoice_date)
    if dd is not None and dd <= config.DUP_DATE_WINDOW_DAYS:
        score += config.DUP_WEIGHT_DATE
    # invoice number similarity (Jaro-Winkler)
    a, b = normalize_invoice_no(extract.invoice_number), normalize_invoice_no(hist.invoice_number)
    if a and b and JaroWinkler.similarity(a, b) >= config.DUP_INVOICE_JW_THRESHOLD:
        score += config.DUP_WEIGHT_INVOICE_NO
    # line-item similarity (token_set_ratio)
    fp = _line_fingerprint(extract)
    if fp and hist.line_fingerprint and token_set_ratio(fp, hist.line_fingerprint) >= config.DUP_LINE_ITEMS_THRESHOLD:
        score += config.DUP_WEIGHT_LINE_ITEMS
    return score


def check(extract: InvoiceExtract, historical: list[HistoricalInvoice],
          vendor_id: str | None = None) -> list[Reason]:
    amount = extract.total if extract.total is not None else extract.subtotal
    if amount is None or not historical:
        return []

    same_vendor = [h for h in historical if vendor_id is None or h.vendor_id == vendor_id]
    inv_no = normalize_invoice_no(extract.invoice_number)

    # ── exact duplicate → REJECT ──
    for h in same_vendor:
        if not inv_no or normalize_invoice_no(h.invoice_number) != inv_no:
            continue
        if abs(amount - h.amount) > config.DUP_EXACT_AMOUNT_ABS:
            continue
        dd = _days_apart(extract.invoice_date, h.invoice_date)
        if dd is None or dd <= config.DUP_EXACT_DATE_WINDOW_DAYS:
            return [Reason(
                code=ReasonCode.REJECT_DUP_EXACT,
                severity=Severity.REJECT,
                message=(f"Exact duplicate of prior invoice {h.invoice_number} "
                         f"(same vendor, amount ${amount:,.2f}, dates {extract.invoice_date} vs "
                         f"{h.invoice_date})."),
                rule=_RULE_EXACT,
                values={"matched_invoice": h.invoice_number, "amount": amount,
                        "invoice_date": extract.invoice_date, "prior_date": h.invoice_date},
            )]

    # ── fuzzy resubmission → HOLD ──
    best_score, best_h = 0, None
    for h in same_vendor:
        s = _fuzzy_score(extract, amount, h)
        if s > best_score:
            best_score, best_h = s, h

    if best_h is not None and best_score >= config.DUP_FUZZY_HOLD_SCORE:
        return [Reason(
            code=ReasonCode.HOLD_DUP_FUZZY,
            severity=Severity.HOLD,
            message=(f"Possible resubmission of invoice {best_h.invoice_number} "
                     f"(fuzzy score {best_score}/100 ≥ {config.DUP_FUZZY_HOLD_SCORE}): "
                     f"amount ${amount:,.2f} vs ${best_h.amount:,.2f}, "
                     f"dates {extract.invoice_date} vs {best_h.invoice_date})."),
            rule=_RULE_FUZZY,
            values={"matched_invoice": best_h.invoice_number, "score": best_score,
                    "amount": amount, "prior_amount": best_h.amount},
        )]
    return []
