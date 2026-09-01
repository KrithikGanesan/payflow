from app.contracts import ReasonCode
from app.engine import coding
from conftest import make_extract, make_vendor


def _codes(reasons):
    return {r.code for r in reasons}


def test_vendor_defaults_high_confidence():
    v = make_vendor(default_gl_account="6000-Software", default_cost_center="CC-ENG")
    gl, reasons = coding.predict(make_extract(), v, [])
    assert gl.account == "6000-Software"
    assert gl.cost_center == "CC-ENG"
    assert gl.confidence >= 0.80
    assert ReasonCode.HOLD_CODING_LOW_CONF not in _codes(reasons)


def test_missing_defaults_low_confidence_holds():
    v = make_vendor(default_gl_account=None, default_cost_center=None)
    gl, reasons = coding.predict(make_extract(), v, [])
    assert gl.confidence < 0.80
    assert ReasonCode.HOLD_CODING_LOW_CONF in _codes(reasons)


def test_no_vendor_low_confidence_holds():
    gl, reasons = coding.predict(make_extract(), None, [])
    assert gl.confidence < 0.80
    assert ReasonCode.HOLD_CODING_LOW_CONF in _codes(reasons)


def test_partial_defaults_holds():
    v = make_vendor(default_gl_account="6000-Software", default_cost_center=None)
    gl, reasons = coding.predict(make_extract(), v, [])
    assert gl.account == "6000-Software"
    assert ReasonCode.HOLD_CODING_LOW_CONF in _codes(reasons)
