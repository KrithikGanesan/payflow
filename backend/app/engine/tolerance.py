"""Price/total tolerance reconciliation: invoice vs purchase order.

Compares the invoice **subtotal** (goods/services value) against the PO total.
Tax and freight are treated separately — a legitimate tax on a subtotal that
matches the PO must NOT trip a tolerance hold. Auto-clears only within the
*tighter* of ±1% or $25; anything beyond → HOLD_TOLERANCE citing both values.

Pure: (InvoiceExtract, PurchaseOrder|None) -> list[Reason].
"""
from __future__ import annotations

from app.contracts import InvoiceExtract, PurchaseOrder, Reason, ReasonCode, Severity
from . import config

_RULE = "tolerance ±1% AND ≤$25 (whichever tighter)"


def allowed_variance(po_total: float) -> float:
    """The tighter of the two bounds for this PO."""
    return min(config.TOLERANCE_ABS, abs(po_total) * config.TOLERANCE_PCT)


def check(extract: InvoiceExtract, po: PurchaseOrder | None) -> list[Reason]:
    if po is None:
        return []

    # goods/services value on the invoice = subtotal (fall back to total if absent)
    billed = extract.subtotal if extract.subtotal is not None else extract.total
    if billed is None:
        return []  # nothing to reconcile — missing-field gate handles this

    po_total = po.po_total
    variance = round(billed - po_total, 2)
    allowed = allowed_variance(po_total)
    pct = (variance / po_total) if po_total else 0.0

    # Only an *over-charge* beyond tolerance is a payment risk. Under-billing
    # (variance < 0) is a legitimate partial/split bill — never a tolerance hold;
    # cumulative over-billing across split invoices is matching.py's guard.
    if variance <= allowed + 1e-9:
        if variance < -allowed:
            msg = (f"Partial billing: subtotal ${billed:,.2f} is under PO {po.po_number} "
                   f"${po_total:,.2f} ({pct:+.2%}); within PO, no over-charge.")
        else:
            msg = (f"Subtotal ${billed:,.2f} matches PO {po.po_number} ${po_total:,.2f} "
                   f"(variance ${variance:,.2f} = {pct:+.2%}, within tolerance).")
        return [Reason(
            code=ReasonCode.OK_MATCH,
            severity=Severity.INFO,
            message=msg,
            rule=_RULE,
            values={"subtotal": billed, "po_total": po_total, "variance": variance, "pct": round(pct, 4)},
        )]

    return [Reason(
        code=ReasonCode.HOLD_TOLERANCE,
        severity=Severity.HOLD,
        message=(f"Subtotal ${billed:,.2f} vs PO {po.po_number} ${po_total:,.2f} = "
                 f"{pct:+.2%} (${variance:,.2f}), over the {_RULE} "
                 f"(allowed ±${allowed:,.2f}). Tax/freight excluded from this check."),
        rule=_RULE,
        values={"subtotal": billed, "po_total": po_total, "variance": variance,
                "pct": round(pct, 4), "allowed": allowed},
    )]
