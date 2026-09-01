"""2-way (services) and 3-way (goods) PO matching + over-billing guard.

- 2-way: invoice ↔ PO (services; no goods receipt expected).
- 3-way: invoice ↔ PO ↔ goods receipt (PO.requires_goods_receipt). Billing may
  not exceed goods actually received.
- Cumulative-billing / over-billing guard for split-PO: the running total billed
  against a PO may not exceed PO × (1 + tolerance); beyond → HOLD_OVERBILL.

Pure: (InvoiceExtract, PurchaseOrder|None, GoodsReceipt|None) -> list[Reason].
"""
from __future__ import annotations

from app.contracts import GoodsReceipt, InvoiceExtract, PurchaseOrder, Reason, ReasonCode, Severity
from . import config

_RULE_CUM = "Σ billed ≤ PO × (1 + 1%)"
_RULE_3WAY = "3-way match: billed ≤ goods received"
_RULE_AWAIT = "3-way: awaiting goods receipt"


def _billed(extract: InvoiceExtract) -> float:
    val = extract.subtotal if extract.subtotal is not None else extract.total
    return float(val) if val is not None else 0.0


def cumulative_after(extract: InvoiceExtract, po: PurchaseOrder) -> float:
    """Running total billed against the PO once this invoice posts."""
    return round(po.cumulative_billed + _billed(extract), 2)


def check(extract: InvoiceExtract, po: PurchaseOrder | None,
          goods_receipt: GoodsReceipt | None) -> list[Reason]:
    if po is None:
        return []

    reasons: list[Reason] = []
    billed = _billed(extract)
    cum = cumulative_after(extract, po)
    cap = round(po.po_total * (1 + config.TOLERANCE_PCT), 2)
    three_way = po.requires_goods_receipt

    # ── over-billing guard (split-PO cumulative) ──
    if cum > cap + 1e-9:
        reasons.append(Reason(
            code=ReasonCode.HOLD_OVERBILL,
            severity=Severity.HOLD,
            message=(f"Cumulative billing against PO {po.po_number} would reach "
                     f"${cum:,.2f} (prior ${po.cumulative_billed:,.2f} + this ${billed:,.2f}), "
                     f"exceeding PO ${po.po_total:,.2f} + 1% (cap ${cap:,.2f})."),
            rule=_RULE_CUM,
            values={"cumulative_after": cum, "po_total": po.po_total,
                    "prior_billed": po.cumulative_billed, "this_invoice": billed, "cap": cap},
        ))

    # ── 3-way: compare against goods received ──
    if three_way:
        if goods_receipt is None:
            reasons.append(Reason(
                code=ReasonCode.HOLD_AWAITING_RECEIPT,
                severity=Severity.HOLD,
                message=(f"Invoice for ${billed:,.2f} arrived before any goods receipt was posted "
                         f"against PO {po.po_number} (3-way). Hold until the receipt lands — not a "
                         f"reject; the goods may simply be in transit."),
                rule=_RULE_AWAIT,
                values={"this_invoice": billed, "received_total": None},
            ))
        else:
            allowed = round(goods_receipt.received_total * (1 + config.TOLERANCE_PCT), 2)
            if billed > allowed + 1e-9:
                reasons.append(Reason(
                    code=ReasonCode.HOLD_OVERBILL,
                    severity=Severity.HOLD,
                    message=(f"Invoice bills ${billed:,.2f} but goods receipt {goods_receipt.gr_id} "
                             f"records only ${goods_receipt.received_total:,.2f} received on PO "
                             f"{po.po_number} (3-way mismatch)."),
                    rule=_RULE_3WAY,
                    values={"this_invoice": billed, "received_total": goods_receipt.received_total},
                ))

    # ── clean match note ──
    if not reasons:
        kind = "3-way" if three_way else "2-way"
        vals = {"po_total": po.po_total, "cumulative_after": cum, "this_invoice": billed}
        recv = ""
        if three_way and goods_receipt is not None:
            vals["received_total"] = goods_receipt.received_total
            recv = f" Goods received ${goods_receipt.received_total:,.2f} ({goods_receipt.gr_id})."
        reasons.append(Reason(
            code=ReasonCode.OK_MATCH,
            severity=Severity.INFO,
            message=(f"{kind} match to PO {po.po_number}: billed ${billed:,.2f}, "
                     f"cumulative ${cum:,.2f} of ${po.po_total:,.2f}.{recv}"),
            rule=f"{kind} match",
            values=vals,
        ))
    return reasons
