from app.contracts import ReasonCode, Severity
from app.engine import anomaly
from conftest import make_extract, make_hist


def _codes(reasons):
    return {r.code for r in reasons}


def _hist(amounts):
    return [make_hist(invoice_number=f"H{i}", amount=a) for i, a in enumerate(amounts)]


def test_normal_spend_no_anomaly():
    hist = _hist([1000, 1100, 950, 1050])
    assert anomaly.check(make_extract(total=1075.0), hist) == []


def test_burst_over_mean_multiplier_holds():
    # mean ~1000, invoice 8000 = 8x mean -> HOLD
    hist = _hist([1000, 1000, 1000, 1000])
    reasons = anomaly.check(make_extract(total=8000.0), hist)
    r = next(x for x in reasons if x.code == ReasonCode.HOLD_ANOMALY)
    assert r.severity == Severity.HOLD
    assert "8000" in r.message.replace(",", "")


def test_over_max_multiplier_holds():
    # mean not tripped (values vary) but > 2x max
    hist = _hist([500, 1000, 1500, 2000])  # max 2000, mean 1250
    reasons = anomaly.check(make_extract(total=4500.0), hist)  # 3.6x mean AND >2x max
    assert ReasonCode.HOLD_ANOMALY in _codes(reasons)


def test_insufficient_history_skips():
    assert anomaly.check(make_extract(total=99999.0), _hist([1000])) == []
    assert anomaly.check(make_extract(total=99999.0), []) == []
