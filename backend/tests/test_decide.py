"""Integration tests through decide.decide — the featured demo edge cases,
plus happy-path APPROVE, a REJECT, and precedence."""
from app.contracts import Decision, DocType, ReasonCode, Severity
from app.engine import decide
from conftest import make_extract, make_vendor, make_po, make_gr, make_hist


def _codes(result):
    return {r.code for r in result.reasons}


# ─────────────────────── happy path ───────────────────────
def test_happy_path_clean_match_approves():
    v = make_vendor()
    po = make_po(po_total=1000.0)
    result = decide.decide(make_extract(subtotal=1000.0, total=1000.0), vendors=[v], po=po,
                           historical_invoices=[make_hist(amount=1000.0), make_hist(amount=1050.0)])
    assert result.decision == Decision.APPROVE
    assert result.matched_po == "PO-500"
    assert result.gl_coding is not None and result.gl_coding.account == "6000-Software"
    assert result.materiality_band == "<5k"
    assert result.routed_to == "manager"


# ─────────────────────── edge 1: split-PO partial billing ───────────────────────
def test_edge_split_po_overbilling_holds():
    v = make_vendor()
    po = make_po(po_total=10000.0, cumulative_billed=8000.0)
    result = decide.decide(make_extract(subtotal=4000.0, total=4000.0), vendors=[v], po=po)
    assert result.decision == Decision.HOLD
    assert ReasonCode.HOLD_OVERBILL in _codes(result)
    assert result.cumulative_after == 12000.0


def test_edge_split_po_within_cap_approves():
    v = make_vendor()
    po = make_po(po_total=10000.0, cumulative_billed=6000.0)
    result = decide.decide(make_extract(subtotal=4000.0, total=4000.0), vendors=[v], po=po,
                           historical_invoices=[make_hist(amount=3000.0), make_hist(amount=3000.0)])
    assert result.decision == Decision.APPROVE
    assert result.cumulative_after == 10000.0


# ─────────────────────── edge 2: fuzzy duplicate ───────────────────────
def test_edge_fuzzy_duplicate_holds():
    v = make_vendor()
    po = make_po(po_total=1000.0)
    hist = [make_hist(invoice_number="INV-0900", amount=1000.0, invoice_date="2026-08-02",
                      line_fingerprint="cloud hosting")]
    ext = make_extract(invoice_number="INV-7777", subtotal=1000.0, total=1000.0, invoice_date="2026-08-01")
    result = decide.decide(ext, vendors=[v], po=po, historical_invoices=hist)
    assert result.decision == Decision.HOLD
    assert ReasonCode.HOLD_DUP_FUZZY in _codes(result)


# ─────────────────────── edge 3: tax / total over tolerance ───────────────────────
def test_edge_over_tolerance_holds():
    v = make_vendor()
    po = make_po(po_total=10000.0)
    result = decide.decide(make_extract(subtotal=10300.0, total=10300.0), vendors=[v], po=po,
                           historical_invoices=[make_hist(amount=10000.0), make_hist(amount=9800.0)])
    assert result.decision == Decision.HOLD
    assert ReasonCode.HOLD_TOLERANCE in _codes(result)


# ─────────────────────── edge 4: low-confidence extraction ───────────────────────
def test_edge_low_confidence_holds():
    v = make_vendor()
    po = make_po(po_total=1000.0)
    ext = make_extract(subtotal=1000.0, total=1000.0,
                       confidence={"vendor_name": 0.55, "total": 0.60, "invoice_number": 0.5})
    result = decide.decide(ext, vendors=[v], po=po)
    assert result.decision == Decision.HOLD
    assert ReasonCode.HOLD_LOW_CONFIDENCE in _codes(result)
    assert result.overall_confidence < 0.80


# ─────────────────────── edge 5: PO-bypass + notify ───────────────────────
def test_edge_po_bypass_approves_and_notifies():
    v = make_vendor(approved=True, po_bypass_allowed=True)
    ext = make_extract(po_number=None, subtotal=250.0, total=250.0)
    result = decide.decide(ext, vendors=[v], po=None,
                           historical_invoices=[make_hist(amount=200.0), make_hist(amount=300.0)])
    assert result.decision == Decision.APPROVE
    assert ReasonCode.OK_BYPASS in _codes(result)
    assert any(n.type == "bypass_notice" for n in result.notifications)


# ─────────────────────── edge 6: spend anomaly ───────────────────────
def test_edge_spend_anomaly_holds():
    v = make_vendor()
    po = make_po(po_total=25000.0)
    hist = [make_hist(amount=1000.0), make_hist(amount=1200.0), make_hist(amount=900.0)]
    result = decide.decide(make_extract(subtotal=25000.0, total=25000.0), vendors=[v], po=po,
                           historical_invoices=hist)
    assert result.decision == Decision.HOLD
    assert ReasonCode.HOLD_ANOMALY in _codes(result)


# ─────────────────────── REJECT cases ───────────────────────
def test_reject_exact_duplicate():
    v = make_vendor()
    po = make_po(po_total=1000.0)
    hist = [make_hist(invoice_number="INV-1001", amount=1000.0, invoice_date="2026-08-01")]
    ext = make_extract(invoice_number="INV-1001", subtotal=1000.0, total=1000.0, invoice_date="2026-08-01")
    result = decide.decide(ext, vendors=[v], po=po, historical_invoices=hist)
    assert result.decision == Decision.REJECT
    assert ReasonCode.REJECT_DUP_EXACT in _codes(result)


def test_reject_not_an_invoice():
    result = decide.decide(make_extract(doc_type=DocType.STATEMENT), vendors=[make_vendor()], po=make_po())
    assert result.decision == Decision.REJECT
    assert ReasonCode.REJECT_NOT_INVOICE in _codes(result)


def test_reject_expired_po():
    v = make_vendor()
    result = decide.decide(make_extract(subtotal=1000.0, total=1000.0), vendors=[v],
                           po=make_po(status="expired"))
    assert result.decision == Decision.REJECT
    assert ReasonCode.REJECT_PO_EXPIRED in _codes(result)


# ─────────────────────── precedence ───────────────────────
def test_precedence_reject_beats_hold():
    # unapproved vendor (HOLD) + exact duplicate (REJECT) -> REJECT wins
    v = make_vendor(approved=False)
    po = make_po(po_total=1000.0)
    hist = [make_hist(invoice_number="INV-1001", amount=1000.0, invoice_date="2026-08-01")]
    ext = make_extract(invoice_number="INV-1001", subtotal=1000.0, total=1000.0, invoice_date="2026-08-01")
    result = decide.decide(ext, vendors=[v], po=po, historical_invoices=hist)
    assert result.decision == Decision.REJECT


def test_precedence_hold_beats_approve():
    # clean match but unapproved vendor -> HOLD
    v = make_vendor(approved=False)
    po = make_po(po_total=1000.0)
    result = decide.decide(make_extract(subtotal=1000.0, total=1000.0), vendors=[v], po=po)
    assert result.decision == Decision.HOLD
    assert ReasonCode.HOLD_VENDOR_UNAPPROVED in _codes(result)


def test_bank_change_routes_high_dollar_to_cfo():
    v = make_vendor(bank_account_hash="hash-original")
    po = make_po(po_total=150000.0)
    ext = make_extract(subtotal=150000.0, total=150000.0, remit_to_bank="hash-NEW")
    result = decide.decide(ext, vendors=[v], po=po,
                           historical_invoices=[make_hist(amount=140000.0), make_hist(amount=160000.0)])
    assert result.decision == Decision.HOLD
    assert ReasonCode.HOLD_BANK_CHANGE in _codes(result)
    assert result.materiality_band == ">100k"
    assert result.routed_to == "CFO"
