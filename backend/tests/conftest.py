"""Pytest config + factory helpers for the Verdict decision-engine tests.

Adds the backend dir to sys.path so `import app.*` resolves when pytest is
launched from the repo root (`python -m pytest backend/tests`).
"""
from __future__ import annotations
import os
import sys

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.contracts import (  # noqa: E402
    DocType,
    GoodsReceipt,
    HistoricalInvoice,
    InvoiceExtract,
    LineItem,
    POLine,
    PurchaseOrder,
    Vendor,
)


# ─────────────────────────── factories ───────────────────────────
def make_extract(**kw) -> InvoiceExtract:
    """A clean, high-confidence services invoice unless overridden."""
    defaults = dict(
        doc_type=DocType.INVOICE,
        vendor_name="Acme Cloud Services",
        invoice_number="INV-1001",
        invoice_date="2026-08-01",
        po_number="PO-500",
        currency="USD",
        line_items=[LineItem(description="Cloud hosting", quantity=1, unit_price=1000.0, amount=1000.0)],
        subtotal=1000.0,
        tax_total=0.0,
        freight=0.0,
        discount=0.0,
        total=1000.0,
        confidence={"vendor_name": 0.98, "total": 0.97, "invoice_number": 0.96},
    )
    defaults.update(kw)
    return InvoiceExtract(**defaults)


def make_vendor(**kw) -> Vendor:
    defaults = dict(
        vendor_id="V-1",
        legal_name="Acme Cloud Services Inc.",
        normalized_name="acme cloud services",
        approved=True,
        po_bypass_allowed=False,
        category="software",
        default_gl_account="6000-Software",
        default_cost_center="CC-ENG",
        bank_account_hash="hash-abc",
    )
    defaults.update(kw)
    return Vendor(**defaults)


def make_po(**kw) -> PurchaseOrder:
    defaults = dict(
        po_number="PO-500",
        vendor_id="V-1",
        currency="USD",
        po_total=1000.0,
        lines=[POLine(description="Cloud hosting", quantity=1, unit_price=1000.0, line_total=1000.0)],
        status="open",
        requires_goods_receipt=False,
        cumulative_billed=0.0,
    )
    defaults.update(kw)
    return PurchaseOrder(**defaults)


def make_gr(**kw) -> GoodsReceipt:
    defaults = dict(gr_id="GR-1", po_number="PO-500", received_total=1000.0, received_date="2026-07-30")
    defaults.update(kw)
    return GoodsReceipt(**defaults)


def make_hist(**kw) -> HistoricalInvoice:
    defaults = dict(
        vendor_id="V-1",
        invoice_number="INV-0900",
        amount=1000.0,
        invoice_date="2026-06-01",
        line_fingerprint="cloud hosting",
    )
    defaults.update(kw)
    return HistoricalInvoice(**defaults)
