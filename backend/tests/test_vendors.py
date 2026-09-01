from app.contracts import ReasonCode, Severity
from app.engine import vendors
from conftest import make_extract, make_vendor


def _codes(reasons):
    return {r.code for r in reasons}


def test_strong_name_match_auto_clears():
    v = make_vendor(legal_name="Acme Cloud Services Inc.", normalized_name="acme cloud services")
    ext = make_extract(vendor_name="Acme Cloud Services")
    reasons, matched = vendors.check(ext, [v])
    assert matched is not None and matched.vendor_id == v.vendor_id
    assert ReasonCode.HOLD_VENDOR_FUZZY not in _codes(reasons)
    assert ReasonCode.HOLD_VENDOR_UNAPPROVED not in _codes(reasons)


def test_unapproved_vendor_holds():
    v = make_vendor(approved=False, normalized_name="acme cloud services", legal_name="Acme Cloud Services")
    reasons, matched = vendors.check(make_extract(vendor_name="Acme Cloud Services"), [v])
    assert ReasonCode.HOLD_VENDOR_UNAPPROVED in _codes(reasons)


def test_no_confident_match_holds_as_unapproved():
    v = make_vendor(normalized_name="globex industrial supply", legal_name="Globex Industrial Supply")
    reasons, matched = vendors.check(make_extract(vendor_name="Totally Unknown Vendor LLC"), [v])
    assert ReasonCode.HOLD_VENDOR_UNAPPROVED in _codes(reasons)


def test_mid_band_fuzzy_match_holds_for_review():
    # close but not >=92 -> 80..92 band -> HOLD_VENDOR_FUZZY
    v = make_vendor(normalized_name="northwind trading company",
                    legal_name="Northwind Trading Company")
    reasons, matched = vendors.check(make_extract(vendor_name="Northwind Traders Co"), [v])
    assert ReasonCode.HOLD_VENDOR_FUZZY in _codes(reasons)


def test_bank_change_flag():
    v = make_vendor(bank_account_hash="hash-original", normalized_name="acme cloud services",
                    legal_name="Acme Cloud Services")
    ext = make_extract(vendor_name="Acme Cloud Services", remit_to_bank="hash-DIFFERENT")
    reasons, matched = vendors.check(ext, [v])
    bank = next(r for r in reasons if r.code == ReasonCode.HOLD_BANK_CHANGE)
    assert bank.severity == Severity.HOLD


def test_matching_bank_no_flag():
    v = make_vendor(bank_account_hash="hash-abc", normalized_name="acme cloud services",
                    legal_name="Acme Cloud Services")
    ext = make_extract(vendor_name="Acme Cloud Services", remit_to_bank="hash-abc")
    reasons, matched = vendors.check(ext, [v])
    assert ReasonCode.HOLD_BANK_CHANGE not in _codes(reasons)
