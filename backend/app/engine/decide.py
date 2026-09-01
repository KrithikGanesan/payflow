"""Decision orchestrator — the spine.

Runs every gate over (extract, master data), collects Reasons, then applies
PRECEDENCE (most-severe outcome wins): any REJECT → REJECT; else any HOLD →
HOLD; else APPROVE. Computes overall_confidence, materiality band, DOA routing,
GL coding, matched PO, cumulative-after, and notifications.

Pure: no I/O. Inputs are contracts objects; output is a DecisionResult.
"""
from __future__ import annotations

from app.contracts import (
    Decision, DecisionResult, GLCoding, HistoricalInvoice, InvoiceExtract,
    Notification, PurchaseOrder, GoodsReceipt, Reason, ReasonCode, Severity, Vendor,
)
from . import anomaly, coding, duplicates, matching, policy, tolerance


def _amount(extract: InvoiceExtract) -> float | None:
    return extract.total if extract.total is not None else extract.subtotal


def _overall_confidence(extract: InvoiceExtract, gl: GLCoding | None) -> float:
    conf = extract.confidence or {}
    extraction = min(conf.values()) if conf else 1.0
    coding_conf = gl.confidence if gl else 1.0
    return round(min(extraction, coding_conf), 4)


def _precedence(reasons: list[Reason]) -> Decision:
    sev = {r.severity for r in reasons}
    if Severity.REJECT in sev:
        return Decision.REJECT
    if Severity.HOLD in sev:
        return Decision.HOLD
    return Decision.APPROVE


def decide(
    extract: InvoiceExtract,
    vendors: list[Vendor] | None = None,
    po: PurchaseOrder | None = None,
    goods_receipt: GoodsReceipt | None = None,
    historical_invoices: list[HistoricalInvoice] | None = None,
) -> DecisionResult:
    vendors = vendors or []
    historical_invoices = historical_invoices or []
    reasons: list[Reason] = []
    notifications: list[Notification] = []
    amount = _amount(extract)

    # ── hard reject gates (short-circuit garbage before deeper analysis) ──
    early = policy.document_type(extract) + policy.missing_critical(extract)
    if early:
        return DecisionResult(
            decision=Decision.REJECT,
            reasons=early,
            overall_confidence=_overall_confidence(extract, None),
            materiality_band=policy.materiality_band(amount),
            routed_to=None,
            matched_po=po.po_number if po else None,
        )

    # ── vendor gate (also yields the matched vendor for coding/anomaly/bypass) ──
    # NB: the `vendors` param shadows the engine.vendors module, so resolve it lazily.
    vendor_reasons, matched_vendor = _run_vendor(extract, vendors)
    reasons += vendor_reasons

    # ── GL coding ──
    gl, coding_reasons = coding.predict(extract, matched_vendor, historical_invoices)
    reasons += coding_reasons

    # ── PO reject gate ──
    reasons += policy.po_status(po)

    # ── credit memo: route separately, skip financial matching ──
    cm_reasons = policy.credit_memo(extract)
    reasons += cm_reasons

    # ── extraction confidence / arithmetic ──
    reasons += policy.confidence_gate(extract)

    # ── currency ──
    reasons += policy.currency(extract, po)

    # ── duplicates ──
    vendor_id = matched_vendor.vendor_id if matched_vendor else None
    reasons += duplicates.check(extract, historical_invoices, vendor_id=vendor_id)

    cumulative_after = None
    if not cm_reasons:
        # ── matching + tolerance (PO invoices) ──
        reasons += matching.check(extract, po, goods_receipt)
        reasons += tolerance.check(extract, po)
        if po is not None:
            cumulative_after = matching.cumulative_after(extract, po)
        # ── PO-bypass / no-PO handling ──
        bypass_reasons, bypass_notes = policy.po_bypass(extract, matched_vendor, po)
        reasons += bypass_reasons
        notifications += bypass_notes
        # ── spend anomaly & split-threshold ──
        vendor_hist = [h for h in historical_invoices if h.vendor_id == vendor_id] if vendor_id else []
        reasons += anomaly.check(extract, vendor_hist)
        reasons += policy.split_threshold(extract, vendor_hist)

    # ── precedence ──
    decision = _precedence(reasons)
    if decision == Decision.APPROVE and not any(r.severity == Severity.INFO for r in reasons):
        reasons.append(Reason(
            code=ReasonCode.OK_CLEAN,
            severity=Severity.INFO,
            message="All gates passed; clean invoice.",
            rule="clean",
        ))

    # ── routing ──
    routed_to = policy.route_for(amount)
    band = policy.materiality_band(amount)
    if decision in (Decision.HOLD, Decision.APPROVE):
        notifications.append(Notification(
            type="approver_route",
            recipient=routed_to,
            message=(f"{decision.value} · ${amount:,.2f} ({band}) routed to {routed_to} per DOA."
                     if amount is not None else f"{decision.value} routed to {routed_to} per DOA."),
        ))
    # surface bank-change as an explicit fraud flag
    if any(r.code == ReasonCode.HOLD_BANK_CHANGE for r in reasons):
        notifications.append(Notification(
            type="fraud_flag",
            recipient="ap-controls",
            message="Remit-to bank change detected — verify vendor bank details out-of-band.",
        ))

    return DecisionResult(
        decision=decision,
        reasons=reasons,
        overall_confidence=_overall_confidence(extract, gl),
        materiality_band=band,
        routed_to=routed_to,
        gl_coding=gl,
        matched_po=po.po_number if po else None,
        cumulative_after=cumulative_after,
        notifications=notifications,
    )


def _run_vendor(extract: InvoiceExtract, vendor_list: list[Vendor]):
    from . import vendors as vendors_mod
    return vendors_mod.check(extract, vendor_list)
