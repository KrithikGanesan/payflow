"""Post-extraction validation & confidence calibration.

Runs *after* a provider returns an ``InvoiceExtract`` and before the decision
engine sees it. Three jobs:

1. **Arithmetic** — do the numbers add up?
   - Σ line_items.amount ≈ subtotal
   - subtotal + tax + freight − discount ≈ total
   Results land in ``extract.validation`` as ``line_items_sum_ok`` /
   ``subtotal_plus_tax_ok`` (the two keys the decision engine reads).

2. **Format plausibility** — currency is ISO 4217, dates parse, tax rate is in
   a sane band (0..30%). Failures pull down the *per-field* confidence for the
   offending field so downstream gates can see which field is shaky.

3. **Overall confidence signal** — combine the provider's self-reported
   per-field confidence with the arithmetic outcome. Arithmetic failure
   strongly lowers it (a document whose totals don't reconcile is not one we
   trust, however confident the model claimed to be). Stored under the reserved
   key ``confidence["_overall"]`` (underscore keys are meta, not real fields).

Pure and idempotent: safe to re-run on a cache hit.
"""
from __future__ import annotations

from typing import Optional

from dateutil import parser as date_parser

try:
    from ..contracts import InvoiceExtract
except ImportError:  # pragma: no cover
    from app.contracts import InvoiceExtract  # type: ignore


# Small mixed absolute+relative tolerance for money comparisons.
ABS_EPS = 0.01          # one cent
REL_EPS = 0.005         # 0.5% of the larger magnitude
OVERALL_KEY = "_overall"

# Minimal but broad ISO 4217 code set (extend as needed).
ISO_4217 = {
    "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY", "INR", "SGD",
    "HKD", "NZD", "SEK", "NOK", "DKK", "ZAR", "AED", "SAR", "MXN", "BRL",
    "KRW", "THB", "MYR", "IDR", "PHP", "PLN", "CZK", "HUF", "ILS", "TRY",
}


def _approx(a: float, b: float, eps_abs: float = ABS_EPS, eps_rel: float = REL_EPS) -> bool:
    return abs(a - b) <= max(eps_abs, eps_rel * max(abs(a), abs(b)))


def _num(x: Optional[float]) -> float:
    return 0.0 if x is None else float(x)


def _lower_field_conf(extract: InvoiceExtract, field: str, ceiling: float) -> None:
    """Cap a field's self-reported confidence (format check failed)."""
    cur = extract.confidence.get(field, ceiling)
    extract.confidence[field] = min(cur, ceiling)


# ─────────────────────────── individual checks ───────────────────────────

def check_line_items_sum(extract: InvoiceExtract) -> bool:
    """Σ line_items.amount ≈ subtotal. False if not verifiable."""
    if extract.subtotal is None or not extract.line_items:
        return False
    amounts = [li.amount for li in extract.line_items]
    if any(a is None for a in amounts):
        return False
    return _approx(sum(_num(a) for a in amounts), _num(extract.subtotal))


def check_subtotal_plus_tax(extract: InvoiceExtract) -> bool:
    """subtotal + tax + freight − discount ≈ total. False if not verifiable."""
    if extract.subtotal is None or extract.total is None:
        return False
    computed = (
        _num(extract.subtotal)
        + _num(extract.tax_total)
        + _num(extract.freight)
        - _num(extract.discount)
    )
    return _approx(computed, _num(extract.total))


def check_currency(extract: InvoiceExtract) -> bool:
    """Currency present and a valid ISO 4217 code (case-insensitive)."""
    if not extract.currency:
        return False
    return extract.currency.strip().upper() in ISO_4217


def check_dates(extract: InvoiceExtract) -> dict[str, bool]:
    """Each present date parses. Missing dates are not counted as failures."""
    out: dict[str, bool] = {}
    for field in ("invoice_date", "due_date"):
        val = getattr(extract, field)
        if val is None or str(val).strip() == "":
            continue
        try:
            date_parser.parse(str(val))
            out[field] = True
        except (ValueError, OverflowError, TypeError):
            out[field] = False
    return out


def check_tax_rate(extract: InvoiceExtract) -> bool:
    """Effective tax rate and per-line tax rates plausible (0..30%)."""
    ok = True
    for li in extract.line_items:
        if li.tax_rate is not None and not (0.0 <= li.tax_rate <= 0.30):
            ok = False
    # Derived effective rate from totals, when both present and subtotal != 0.
    if extract.tax_total is not None and extract.subtotal:
        eff = _num(extract.tax_total) / _num(extract.subtotal)
        if not (0.0 <= eff <= 0.30):
            ok = False
    return ok


# ─────────────────────────── overall confidence ───────────────────────────

def _self_reported_mean(extract: InvoiceExtract) -> float:
    vals = [
        v for k, v in extract.confidence.items()
        if not k.startswith("_") and isinstance(v, (int, float))
    ]
    if not vals:
        return 0.5  # provider gave no signal -> neutral prior
    clamped = [min(1.0, max(0.0, float(v))) for v in vals]
    return sum(clamped) / len(clamped)


def compute_overall_confidence(
    extract: InvoiceExtract,
    arithmetic_ok: bool,
    currency_ok: bool,
    dates_ok: bool,
    tax_ok: bool,
) -> float:
    """Fold self-reported confidence together with objective checks.

    Start from the mean self-reported per-field confidence, then apply
    multiplicative penalties. Arithmetic failure is the heaviest hit — a
    document whose money doesn't reconcile should never read as high-confidence.
    """
    overall = _self_reported_mean(extract)

    if not arithmetic_ok:
        # Hard cap + strong multiplicative penalty.
        overall = min(overall, 0.50) * 0.7
    if not currency_ok:
        overall *= 0.90
    if not dates_ok:
        overall *= 0.92
    if not tax_ok:
        overall *= 0.90

    return round(min(1.0, max(0.0, overall)), 4)


# ─────────────────────────── entry point ───────────────────────────

def validate(extract: InvoiceExtract) -> InvoiceExtract:
    """Run all checks, populate ``validation`` and ``confidence['_overall']``.

    Mutates and returns the same object. Idempotent.
    """
    line_items_sum_ok = check_line_items_sum(extract)
    subtotal_plus_tax_ok = check_subtotal_plus_tax(extract)

    extract.validation["line_items_sum_ok"] = line_items_sum_ok
    extract.validation["subtotal_plus_tax_ok"] = subtotal_plus_tax_ok

    currency_ok = check_currency(extract)
    dates = check_dates(extract)
    dates_ok = all(dates.values()) if dates else True
    tax_ok = check_tax_rate(extract)

    # Reflect format failures into per-field confidence for downstream gates.
    if not currency_ok:
        _lower_field_conf(extract, "currency", 0.30)
    for field, parsed in dates.items():
        if not parsed:
            _lower_field_conf(extract, field, 0.30)

    arithmetic_ok = line_items_sum_ok and subtotal_plus_tax_ok
    extract.confidence[OVERALL_KEY] = compute_overall_confidence(
        extract, arithmetic_ok, currency_ok, dates_ok, tax_ok
    )
    return extract
