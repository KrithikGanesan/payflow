"""GL coding: predict account + cost centre from vendor defaults / history.

Confidence is high when the vendor master supplies both the default GL account
and cost centre; partial when only one is known; low when neither is available
(e.g. an unmatched vendor). Below the gate → HOLD_CODING_LOW_CONF so a human
assigns the coding rather than the AI guessing.

Pure: (InvoiceExtract, Vendor|None, list[HistoricalInvoice]) -> (GLCoding, list[Reason]).
"""
from __future__ import annotations

from app.contracts import GLCoding, HistoricalInvoice, InvoiceExtract, Reason, ReasonCode, Severity, Vendor
from . import config

_RULE = f"GL coding confidence ≥ {config.CODING_CONFIDENCE_GATE:.2f}"


def predict(extract: InvoiceExtract, vendor: Vendor | None,
            historical: list[HistoricalInvoice] | None = None) -> tuple[GLCoding, list[Reason]]:
    account = vendor.default_gl_account if vendor else None
    cost_center = vendor.default_cost_center if vendor else None

    if account and cost_center:
        confidence = config.CODING_CONF_FULL
    elif account or cost_center:
        confidence = config.CODING_CONF_PARTIAL
    else:
        confidence = config.CODING_CONF_NONE

    gl = GLCoding(account=account, cost_center=cost_center, confidence=round(confidence, 4))

    reasons: list[Reason] = []
    if confidence < config.CODING_CONFIDENCE_GATE:
        src = f"vendor '{vendor.legal_name}'" if vendor else "no matched vendor"
        reasons.append(Reason(
            code=ReasonCode.HOLD_CODING_LOW_CONF,
            severity=Severity.HOLD,
            message=(f"GL coding confidence {confidence:.2f} < {config.CODING_CONFIDENCE_GATE:.2f} "
                     f"(account={account or '—'}, cost_center={cost_center or '—'} from {src}); "
                     f"needs manual coding."),
            rule=_RULE,
            values={"account": account, "cost_center": cost_center, "confidence": round(confidence, 4)},
        ))
    return gl, reasons
