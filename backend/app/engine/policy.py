"""Policy gates + routing that don't belong to a single artifact check.

Document-type · missing-critical-field · credit-memo · currency · PO status ·
extraction-confidence gate · PO-bypass (+finance notify) · split-threshold, plus
materiality-band and delegation-of-authority (DOA) routing helpers.

All functions are pure and return list[Reason] (po_bypass also returns
Notifications). Materiality/routing helpers return plain values.
"""
from __future__ import annotations

from datetime import date

from app.contracts import (
    DocType, InvoiceExtract, Notification, PurchaseOrder, Reason, ReasonCode, Severity, Vendor,
)
from . import config

CRITICAL_FIELDS = ("vendor_name", "invoice_number", "invoice_date", "total")


# ─────────────────────────── reject gates ───────────────────────────
def document_type(extract: InvoiceExtract) -> list[Reason]:
    if extract.doc_type in (DocType.STATEMENT, DocType.OTHER):
        return [Reason(
            code=ReasonCode.REJECT_NOT_INVOICE,
            severity=Severity.REJECT,
            message=f"Document type is {extract.doc_type.value}, not an invoice; cannot process for payment.",
            rule="document-type gate",
            values={"doc_type": extract.doc_type.value},
        )]
    return []


def missing_critical(extract: InvoiceExtract) -> list[Reason]:
    missing = []
    for f in CRITICAL_FIELDS:
        v = getattr(extract, f, None)
        if v is None or (isinstance(v, str) and not v.strip()):
            missing.append(f)
    if missing:
        return [Reason(
            code=ReasonCode.REJECT_MISSING_CRITICAL,
            severity=Severity.REJECT,
            message=f"Missing critical field(s): {', '.join(missing)}; cannot decide.",
            rule="critical fields required",
            values={"missing": missing},
        )]
    return []


def po_status(po: PurchaseOrder | None) -> list[Reason]:
    if po is not None and po.status in ("closed", "expired"):
        return [Reason(
            code=ReasonCode.REJECT_PO_EXPIRED,
            severity=Severity.REJECT,
            message=f"PO {po.po_number} is {po.status}; cannot bill against it.",
            rule="PO must be open",
            values={"po_number": po.po_number, "status": po.status},
        )]
    return []


# ─────────────────────────── hold gates ───────────────────────────
def credit_memo(extract: InvoiceExtract) -> list[Reason]:
    is_cm = extract.doc_type == DocType.CREDIT_MEMO or (extract.total is not None and extract.total < 0)
    if is_cm:
        return [Reason(
            code=ReasonCode.HOLD_CREDIT_MEMO,
            severity=Severity.HOLD,
            message=(f"Credit memo (total ${extract.total:,.2f}) — routed to AP for offset against "
                     f"open payables, not paid as an invoice." if extract.total is not None
                     else "Credit memo — routed separately from invoice payment."),
            rule="credit memos routed separately",
            values={"doc_type": extract.doc_type.value, "total": extract.total},
        )]
    return []


def currency(extract: InvoiceExtract, po: PurchaseOrder | None) -> list[Reason]:
    if po is not None and extract.currency and extract.currency != po.currency:
        return [Reason(
            code=ReasonCode.HOLD_CURRENCY,
            severity=Severity.HOLD,
            message=(f"Invoice currency {extract.currency} ≠ PO {po.po_number} currency {po.currency}; "
                     f"cannot reconcile amounts without FX confirmation."),
            rule="invoice currency must equal PO currency",
            values={"invoice_currency": extract.currency, "po_currency": po.currency},
        )]
    return []


def confidence_gate(extract: InvoiceExtract) -> list[Reason]:
    # failed arithmetic → never auto-approve
    failed = [k for k, ok in (extract.validation or {}).items() if ok is False]
    if failed:
        return [Reason(
            code=ReasonCode.HOLD_LOW_CONFIDENCE,
            severity=Severity.HOLD,
            message=f"Extraction arithmetic failed ({', '.join(failed)}); cannot auto-approve.",
            rule="arithmetic must reconcile",
            values={"failed": failed},
        )]
    conf = extract.confidence or {}
    if conf:
        low = {k: v for k, v in conf.items() if not k.startswith("_") and v < config.CONFIDENCE_GATE}
        if low:
            worst = min(low.values())
            return [Reason(
                code=ReasonCode.HOLD_LOW_CONFIDENCE,
                severity=Severity.HOLD,
                message=(f"Extraction confidence below {config.CONFIDENCE_GATE:.2f} on "
                         f"{', '.join(sorted(low))} (lowest {worst:.2f}); manual verify before payment."),
                rule=f"per-field confidence ≥ {config.CONFIDENCE_GATE:.2f}",
                values={"low_fields": low, "gate": config.CONFIDENCE_GATE},
            )]
    return []


def po_bypass(extract: InvoiceExtract, vendor: Vendor | None,
              po: PurchaseOrder | None) -> tuple[list[Reason], list[Notification]]:
    if po is not None:
        return [], []  # matching path handles PO invoices

    amount = extract.total if extract.total is not None else extract.subtotal
    amount = amount or 0.0

    # A PO is required above the bypass ceiling.
    if amount >= config.PO_BYPASS_LIMIT:
        return [Reason(
            code=ReasonCode.REJECT_NO_PO_OVER_BYPASS,
            severity=Severity.REJECT,
            message=(f"No PO and amount ${amount:,.2f} ≥ bypass limit ${config.PO_BYPASS_LIMIT:,.2f}; "
                     f"a purchase order is required."),
            rule=f"no-PO auto-approve only < ${config.PO_BYPASS_LIMIT:,.0f}",
            values={"amount": amount, "limit": config.PO_BYPASS_LIMIT},
        )], []

    # Under the ceiling and vendor is bypass-eligible → approve + notify finance.
    if vendor is not None and vendor.approved and vendor.po_bypass_allowed:
        note = Notification(
            type="bypass_notice",
            recipient="finance",
            message=(f"PO-bypass auto-approval: {vendor.legal_name} ${amount:,.2f} (< "
                     f"${config.PO_BYPASS_LIMIT:,.0f}, category '{vendor.category}'). Logged for review."),
        )
        return [Reason(
            code=ReasonCode.OK_BYPASS,
            severity=Severity.INFO,
            message=(f"PO-bypass: approved vendor '{vendor.legal_name}', ${amount:,.2f} < "
                     f"${config.PO_BYPASS_LIMIT:,.0f}; auto-approved with finance notified."),
            rule=f"PO-bypass < ${config.PO_BYPASS_LIMIT:,.0f} + notify finance",
            values={"amount": amount, "limit": config.PO_BYPASS_LIMIT, "vendor_id": vendor.vendor_id},
        )], [note]

    # Under the ceiling but not bypass-eligible → hold for a human approver.
    return [Reason(
        code=ReasonCode.HOLD_MATERIALITY,
        severity=Severity.HOLD,
        message=(f"No PO and vendor not bypass-eligible; ${amount:,.2f} routed to an approver for "
                 f"manual authorization."),
        rule="no-PO, non-bypass invoices need manual approval",
        values={"amount": amount},
    )], []


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def split_threshold(extract: InvoiceExtract, historical: list) -> list[Reason]:
    """Split-to-avoid-threshold: ≥2 invoices, each under the limit, summing over it,
    within a short window."""
    amount = extract.total if extract.total is not None else extract.subtotal
    if amount is None or amount >= config.SPLIT_THRESHOLD:
        return []
    this_date = _parse_date(extract.invoice_date)
    siblings = []
    for h in historical:
        if h.amount is None or h.amount >= config.SPLIT_THRESHOLD:
            continue
        hd = _parse_date(h.invoice_date)
        if this_date is not None and hd is not None and abs((this_date - hd).days) > config.SPLIT_WINDOW_DAYS:
            continue
        siblings.append(h)
    total = amount + sum(h.amount for h in siblings)
    if siblings and total >= config.SPLIT_THRESHOLD:
        return [Reason(
            code=ReasonCode.HOLD_SPLIT_THRESHOLD,
            severity=Severity.HOLD,
            message=(f"{len(siblings) + 1} invoices each < ${config.SPLIT_THRESHOLD:,.0f} within "
                     f"{config.SPLIT_WINDOW_DAYS}d sum to ${total:,.2f} — possible split to dodge the "
                     f"approval threshold."),
            rule="split-to-avoid-threshold (count≥2 · each<limit · sum≥limit)",
            values={"count": len(siblings) + 1, "sum": round(total, 2), "limit": config.SPLIT_THRESHOLD},
        )]
    return []


# ─────────────────────── materiality / DOA routing ───────────────────────
def materiality_band(amount: float | None) -> str:
    a = amount or 0.0
    if a < config.DOA_MANAGER:
        return "<5k"
    if a < config.DOA_DIRECTOR:
        return "5k-25k"
    if a < config.DOA_VP:
        return "25k-100k"
    return ">100k"


def route_for(amount: float | None) -> str:
    a = amount or 0.0
    if a < config.DOA_MANAGER:
        return "manager"
    if a < config.DOA_DIRECTOR:
        return "director"
    if a < config.DOA_VP:
        return "VP"
    return "CFO"
