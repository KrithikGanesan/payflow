from app.contracts import DocType, ReasonCode, Severity
from app.engine import policy
from conftest import make_extract, make_vendor, make_po


def _codes(reasons):
    return {r.code for r in reasons}


# ── document type ──
def test_statement_rejected():
    assert ReasonCode.REJECT_NOT_INVOICE in _codes(policy.document_type(make_extract(doc_type=DocType.STATEMENT)))


def test_other_doc_rejected():
    assert ReasonCode.REJECT_NOT_INVOICE in _codes(policy.document_type(make_extract(doc_type=DocType.OTHER)))


def test_invoice_doc_ok():
    assert policy.document_type(make_extract(doc_type=DocType.INVOICE)) == []


# ── missing critical ──
def test_missing_total_rejected():
    assert ReasonCode.REJECT_MISSING_CRITICAL in _codes(policy.missing_critical(make_extract(total=None)))


def test_missing_vendor_name_rejected():
    assert ReasonCode.REJECT_MISSING_CRITICAL in _codes(policy.missing_critical(make_extract(vendor_name=None)))


def test_complete_invoice_ok():
    assert policy.missing_critical(make_extract()) == []


# ── credit memo ──
def test_credit_memo_doctype_holds():
    assert ReasonCode.HOLD_CREDIT_MEMO in _codes(policy.credit_memo(make_extract(doc_type=DocType.CREDIT_MEMO, total=-500.0)))


def test_negative_total_holds():
    assert ReasonCode.HOLD_CREDIT_MEMO in _codes(policy.credit_memo(make_extract(total=-500.0)))


# ── currency ──
def test_currency_mismatch_holds():
    reasons = policy.currency(make_extract(currency="EUR"), make_po(currency="USD"))
    assert ReasonCode.HOLD_CURRENCY in _codes(reasons)


def test_currency_match_ok():
    assert policy.currency(make_extract(currency="USD"), make_po(currency="USD")) == []


# ── po status ──
def test_expired_po_rejected():
    assert ReasonCode.REJECT_PO_EXPIRED in _codes(policy.po_status(make_po(status="expired")))


def test_closed_po_rejected():
    assert ReasonCode.REJECT_PO_EXPIRED in _codes(policy.po_status(make_po(status="closed")))


def test_open_po_ok():
    assert policy.po_status(make_po(status="open")) == []


# ── confidence gate ──
def test_low_confidence_holds():
    ext = make_extract(confidence={"vendor_name": 0.55, "total": 0.62})
    assert ReasonCode.HOLD_LOW_CONFIDENCE in _codes(policy.confidence_gate(ext))


def test_high_confidence_ok():
    ext = make_extract(confidence={"vendor_name": 0.98, "total": 0.97})
    assert ReasonCode.HOLD_LOW_CONFIDENCE not in _codes(policy.confidence_gate(ext))


def test_failed_arithmetic_holds():
    ext = make_extract(validation={"subtotal_plus_tax_ok": False})
    assert ReasonCode.HOLD_LOW_CONFIDENCE in _codes(policy.confidence_gate(ext))


# ── po bypass ──
def test_bypass_eligible_approves_and_notifies():
    v = make_vendor(approved=True, po_bypass_allowed=True)
    ext = make_extract(po_number=None, total=250.0)
    reasons, notes = policy.po_bypass(ext, v, None)
    assert ReasonCode.OK_BYPASS in _codes(reasons)
    assert any(n.type == "bypass_notice" for n in notes)


def test_no_po_over_bypass_limit_rejected():
    v = make_vendor(approved=True, po_bypass_allowed=True)
    ext = make_extract(po_number=None, total=1500.0)
    reasons, notes = policy.po_bypass(ext, v, None)
    assert ReasonCode.REJECT_NO_PO_OVER_BYPASS in _codes(reasons)


def test_under_limit_not_bypass_eligible_holds():
    v = make_vendor(approved=True, po_bypass_allowed=False)
    ext = make_extract(po_number=None, total=250.0)
    reasons, notes = policy.po_bypass(ext, v, None)
    assert ReasonCode.HOLD_MATERIALITY in _codes(reasons)


def test_bypass_skipped_when_po_present():
    v = make_vendor(approved=True, po_bypass_allowed=True)
    reasons, notes = policy.po_bypass(make_extract(total=250.0), v, make_po())
    assert reasons == [] and notes == []


# ── materiality / routing ──
def test_materiality_bands():
    assert policy.materiality_band(4999.0) == "<5k"
    assert policy.materiality_band(10000.0) == "5k-25k"
    assert policy.materiality_band(50000.0) == "25k-100k"
    assert policy.materiality_band(200000.0) == ">100k"


def test_routing_by_band():
    assert policy.route_for(4999.0) == "manager"
    assert policy.route_for(10000.0) == "director"
    assert policy.route_for(50000.0) == "VP"
    assert policy.route_for(200000.0) == "CFO"
