from app.contracts import ReasonCode, Severity
from app.engine import tolerance
from conftest import make_extract, make_po


def _codes(reasons):
    return {r.code for r in reasons}


def test_subtotal_within_tolerance_clears():
    # subtotal exactly matches PO -> OK, no hold
    reasons = tolerance.check(make_extract(subtotal=1000.0, total=1000.0), make_po(po_total=1000.0))
    assert ReasonCode.HOLD_TOLERANCE not in _codes(reasons)
    assert any(r.severity == Severity.INFO for r in reasons)


def test_within_abs_and_pct_auto_clears():
    # +$10 on a $1000 PO = +1.0% and <=$25 -> tighter bound is $10... within both -> clear
    reasons = tolerance.check(make_extract(subtotal=1010.0, total=1010.0), make_po(po_total=1000.0))
    assert ReasonCode.HOLD_TOLERANCE not in _codes(reasons)


def test_over_dollar_bound_holds_even_if_under_pct():
    # +$30 on a $100000 PO = +0.03% (under 1%) but > $25 -> tighter bound is $25 -> HOLD
    reasons = tolerance.check(make_extract(subtotal=100030.0, total=100030.0), make_po(po_total=100000.0))
    assert ReasonCode.HOLD_TOLERANCE in _codes(reasons)


def test_over_pct_bound_holds_even_if_under_dollar_on_small_po():
    # +$5 on a $100 PO = +5% (> 1%) though only $5 -> tighter bound is 1% ($1) -> HOLD
    reasons = tolerance.check(make_extract(subtotal=105.0, total=105.0), make_po(po_total=100.0))
    assert ReasonCode.HOLD_TOLERANCE in _codes(reasons)


def test_tax_treated_separately_does_not_trigger_tolerance():
    # subtotal matches PO exactly; legitimate tax on top must NOT be a tolerance hold
    ext = make_extract(subtotal=1000.0, tax_total=80.0, total=1080.0)
    reasons = tolerance.check(ext, make_po(po_total=1000.0))
    assert ReasonCode.HOLD_TOLERANCE not in _codes(reasons)


def test_tolerance_hold_cites_both_values():
    reasons = tolerance.check(make_extract(subtotal=10300.0, total=10300.0), make_po(po_total=10000.0))
    hold = next(r for r in reasons if r.code == ReasonCode.HOLD_TOLERANCE)
    assert hold.values.get("subtotal") == 10300.0
    assert hold.values.get("po_total") == 10000.0
    assert "10300" in hold.message.replace(",", "") and "10000" in hold.message.replace(",", "")


def test_no_po_no_tolerance_check():
    assert tolerance.check(make_extract(), None) == []
