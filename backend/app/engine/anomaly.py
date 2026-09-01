"""Spend anomaly vs vendor history.

Compares this invoice's amount to the vendor's historical mean and max. A sudden
burst — > 5× the mean OR > 2× the largest prior invoice — is a fraud/error
instinct trigger → HOLD_ANOMALY. Needs a minimum history to establish a baseline.

Pure: (InvoiceExtract, list[HistoricalInvoice]) -> list[Reason].
"""
from __future__ import annotations

from app.contracts import HistoricalInvoice, InvoiceExtract, Reason, ReasonCode, Severity
from . import config

_RULE = f"> {config.ANOMALY_MEAN_MULTIPLIER:g}× vendor mean or > {config.ANOMALY_MAX_MULTIPLIER:g}× max"


def check(extract: InvoiceExtract, historical: list[HistoricalInvoice]) -> list[Reason]:
    amount = extract.total if extract.total is not None else extract.subtotal
    if amount is None:
        return []

    amounts = [h.amount for h in historical if h.amount is not None]
    if len(amounts) < config.ANOMALY_MIN_HISTORY:
        return []

    mean = sum(amounts) / len(amounts)
    hi = max(amounts)

    over_mean = mean > 0 and amount > config.ANOMALY_MEAN_MULTIPLIER * mean
    over_max = hi > 0 and amount > config.ANOMALY_MAX_MULTIPLIER * hi
    if not (over_mean or over_max):
        return []

    mult_mean = (amount / mean) if mean else float("inf")
    mult_max = (amount / hi) if hi else float("inf")
    return [Reason(
        code=ReasonCode.HOLD_ANOMALY,
        severity=Severity.HOLD,
        message=(f"Invoice ${amount:,.2f} is {mult_mean:.1f}× the vendor mean ${mean:,.2f} "
                 f"and {mult_max:.1f}× the prior max ${hi:,.2f} over {len(amounts)} invoices — "
                 f"spend burst, review."),
        rule=_RULE,
        values={"amount": amount, "mean": round(mean, 2), "max": hi,
                "x_mean": round(mult_mean, 2), "x_max": round(mult_max, 2), "n": len(amounts)},
    )]
