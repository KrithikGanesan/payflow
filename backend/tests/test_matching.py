from app.contracts import ReasonCode, Severity
from app.engine import matching
from conftest import make_extract, make_po, make_gr


def _codes(reasons):
    return {r.code for r in reasons}


def test_two_way_match_ok():
    reasons = matching.check(make_extract(subtotal=1000.0, total=1000.0), make_po(po_total=1000.0), None)
    assert ReasonCode.OK_MATCH in _codes(reasons)
    assert ReasonCode.HOLD_OVERBILL not in _codes(reasons)


def test_split_po_within_cumulative_ok():
    # PO 10000, already billed 6000, this invoice 4000 -> cumulative 10000 <= PO -> OK
    po = make_po(po_total=10000.0, cumulative_billed=6000.0)
    ext = make_extract(subtotal=4000.0, total=4000.0)
    reasons = matching.check(ext, po, None)
    assert ReasonCode.HOLD_OVERBILL not in _codes(reasons)
    assert matching.cumulative_after(ext, po) == 10000.0


def test_split_po_over_billing_holds():
    # PO 10000, already billed 8000, this invoice 4000 -> cumulative 12000 > PO*1.01 -> HOLD_OVERBILL
    po = make_po(po_total=10000.0, cumulative_billed=8000.0)
    ext = make_extract(subtotal=4000.0, total=4000.0)
    reasons = matching.check(ext, po, None)
    hold = next(r for r in reasons if r.code == ReasonCode.HOLD_OVERBILL)
    assert hold.severity == Severity.HOLD
    assert hold.values.get("cumulative_after") == 12000.0
    assert hold.values.get("po_total") == 10000.0


def test_three_way_match_ok_when_goods_received():
    po = make_po(po_total=1000.0, requires_goods_receipt=True)
    gr = make_gr(received_total=1000.0)
    reasons = matching.check(make_extract(subtotal=1000.0, total=1000.0), po, gr)
    assert ReasonCode.HOLD_OVERBILL not in _codes(reasons)
    assert ReasonCode.OK_MATCH in _codes(reasons)


def test_three_way_billing_exceeds_goods_received_holds():
    po = make_po(po_total=5000.0, requires_goods_receipt=True)
    gr = make_gr(received_total=2000.0)  # only 2000 of goods received
    ext = make_extract(subtotal=5000.0, total=5000.0)
    reasons = matching.check(ext, po, gr)
    assert ReasonCode.HOLD_OVERBILL in _codes(reasons)


def test_three_way_missing_goods_receipt_holds():
    po = make_po(po_total=1000.0, requires_goods_receipt=True)
    reasons = matching.check(make_extract(subtotal=1000.0, total=1000.0), po, None)
    assert ReasonCode.HOLD_AWAITING_RECEIPT in _codes(reasons)
    assert ReasonCode.HOLD_OVERBILL not in _codes(reasons)


def test_no_po_returns_empty():
    assert matching.check(make_extract(po_number=None), None, None) == []
