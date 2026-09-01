from app.contracts import ReasonCode, Severity
from app.engine import duplicates
from conftest import make_extract, make_hist


def _codes(reasons):
    return {r.code for r in reasons}


def test_no_history_no_duplicate():
    assert duplicates.check(make_extract(), [], vendor_id="V-1") == []


def test_exact_duplicate_rejects():
    hist = [make_hist(invoice_number="INV-1001", amount=1000.0, invoice_date="2026-08-02")]
    ext = make_extract(invoice_number="INV-1001", total=1000.0, invoice_date="2026-08-01")
    reasons = duplicates.check(ext, hist, vendor_id="V-1")
    r = next(x for x in reasons if x.code == ReasonCode.REJECT_DUP_EXACT)
    assert r.severity == Severity.REJECT


def test_exact_duplicate_normalizes_invoice_number():
    # "inv 1001" vs "INV-1001" normalize equal
    hist = [make_hist(invoice_number="inv 1001", amount=1000.0, invoice_date="2026-08-01")]
    ext = make_extract(invoice_number="INV-1001", total=1000.0, invoice_date="2026-08-01")
    assert ReasonCode.REJECT_DUP_EXACT in _codes(duplicates.check(ext, hist, vendor_id="V-1"))


def test_fuzzy_resubmission_holds():
    # different invoice number, same amount, near date, same line items -> score >=70 -> HOLD
    hist = [make_hist(invoice_number="INV-0900", amount=1000.0, invoice_date="2026-08-03",
                      line_fingerprint="cloud hosting monthly")]
    ext = make_extract(invoice_number="INV-9999", total=1000.0, invoice_date="2026-08-01")
    reasons = duplicates.check(ext, hist, vendor_id="V-1")
    hold = next(r for r in reasons if r.code == ReasonCode.HOLD_DUP_FUZZY)
    assert hold.severity == Severity.HOLD
    assert hold.values.get("matched_invoice") == "INV-0900"


def test_distinct_invoice_not_flagged():
    hist = [make_hist(invoice_number="INV-0001", amount=42.0, invoice_date="2026-01-01",
                      line_fingerprint="totally different widget order")]
    ext = make_extract(invoice_number="INV-9999", total=8888.0, invoice_date="2026-08-01",
                       line_items=[])
    assert duplicates.check(ext, hist, vendor_id="V-1") == []


def test_only_same_vendor_considered():
    hist = [make_hist(vendor_id="V-OTHER", invoice_number="INV-1001", amount=1000.0, invoice_date="2026-08-01")]
    ext = make_extract(invoice_number="INV-1001", total=1000.0, invoice_date="2026-08-01")
    assert duplicates.check(ext, hist, vendor_id="V-1") == []
