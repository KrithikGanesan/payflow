#!/usr/bin/env python
"""Generate the PayFlow test corpus.

Produces, under data/:
  - invoices/*.pdf   : ~13 invoice PDFs, each crafted to trigger ONE AP path.
                       Twelve are text-layer PDFs (reportlab); one is a
                       rasterised image-only "scanned" PDF (Pillow).
  - fixtures/<sha256-of-pdf-bytes>.json : the CORRECT InvoiceExtract for each
                       PDF (ground truth → powers fixture-mode extraction).
  - fixtures/manifest.json : [{filename, sha256, scenario, expected_decision}]

Deterministic: reportlab timestamps are pinned (rl_config.invariant) and the
output dirs are wiped first, so re-running yields stable file names / hashes.

Run:  ./.venv/bin/python scripts/generate_corpus.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# make backend importable so we validate fixtures against the real contracts
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from reportlab import rl_config  # noqa: E402

rl_config.invariant = 1  # pin producer + creation date → reproducible bytes

from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app.contracts import DocType, InvoiceExtract, LineItem  # noqa: E402

INVOICES_DIR = _REPO_ROOT / "data" / "invoices"
FIXTURES_DIR = _REPO_ROOT / "data" / "fixtures"

CURRENCY_SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£"}


# ─────────────────────────── scenario corpus ───────────────────────────
# Each scenario carries the printable invoice content AND the confidence
# profile used to build its ground-truth extract. Totals are internally
# consistent (subtotal + tax + freight - discount == total) unless noted.
def _line(desc, qty, price, tax_rate=None):
    return {"description": desc, "quantity": qty, "unit_price": price,
            "amount": round(qty * price, 2), "tax_rate": tax_rate}


SCENARIOS: list[dict] = [
    {
        "filename": "01_clean_exact.pdf",
        "scenario": "clean_happy_path_exact",
        "expected_decision": "APPROVE",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Acme Corporation Inc.",
        "vendor_address": "500 Innovation Way, San Jose, CA 95110",
        "vendor_tax_id": "US-84-1029384",
        "invoice_number": "ACM-88001",
        "invoice_date": "2026-08-25",
        "due_date": "2026-09-24",
        "po_number": "PO-1001",
        "currency": "USD",
        "lines": [_line("Enterprise Laptop 14in i7/32GB", 10, 1200.00)],
        "subtotal": 12000.00, "tax_total": 0.00, "freight": 0.00, "discount": 0.00,
        "total": 12000.00,
        "payment_terms": "Net 30",
        "remit_to_bank": "sha256:9f2a1c7b0e4d",
        "confidence": "high",
        "note": "Total exactly equals PO-1001 ($12,000); 3-way match w/ GR-9001.",
    },
    {
        "filename": "02_clean_tolerance.pdf",
        "scenario": "clean_within_tolerance",
        "expected_decision": "APPROVE",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Globex Industrial Supply LLC",
        "vendor_address": "18 Harbor Rd, Newark, NJ 07102",
        "vendor_tax_id": "US-77-5566778",
        "invoice_number": "GLBX-4521",
        "invoice_date": "2026-08-26",
        "due_date": "2026-09-25",
        "po_number": "PO-1002",
        "currency": "USD",
        "lines": [
            _line("Industrial shelving unit", 15, 200.00),
            _line("Safety equipment kit", 30, 50.00),
        ],
        "subtotal": 4500.00, "tax_total": 12.00, "freight": 0.00, "discount": 0.00,
        "total": 4512.00,
        "payment_terms": "Net 30",
        "remit_to_bank": "sha256:1b8e3f6a2c90",
        "confidence": "high",
        "note": "Total $4,512 vs PO $4,500 = +$12 (+0.27%): within +/-1% AND <=$25.",
    },
    {
        "filename": "03_split_po_partial.pdf",
        "scenario": "split_po_partial_billing",
        "expected_decision": "APPROVE",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Initech Software Services Inc.",
        "vendor_address": "1 Cubicle Plaza, Austin, TX 78701",
        "vendor_tax_id": "US-22-3344556",
        "invoice_number": "INI-M2",
        "invoice_date": "2026-08-27",
        "due_date": "2026-09-26",
        "po_number": "PO-1003",
        "currency": "USD",
        "lines": [_line("Platform implementation - milestone 2 of 3", 1, 20000.00)],
        "subtotal": 20000.00, "tax_total": 0.00, "freight": 0.00, "discount": 0.00,
        "total": 20000.00,
        "payment_terms": "Net 30",
        "remit_to_bank": "sha256:4c7d9a0b1e23",
        "confidence": "high",
        "note": "PO-1003 already billed $20k of $60k; this $20k -> cum $40k <= $60k.",
    },
    {
        "filename": "04_fuzzy_duplicate.pdf",
        "scenario": "fuzzy_duplicate",
        "expected_decision": "HOLD",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Wayne Consulting Group",
        "vendor_address": "1007 Mountain Dr, Gotham, NY 10001",
        "vendor_tax_id": "US-55-6677889",
        "invoice_number": "INV-WC-2099",
        "invoice_date": "2026-06-18",
        "due_date": "2026-07-18",
        "po_number": "PO-1010",
        "currency": "USD",
        "lines": [_line("Q2 advisory engagement", 50, 150.00)],
        "subtotal": 7500.00, "tax_total": 0.00, "freight": 0.00, "discount": 0.00,
        "total": 7500.00,
        "payment_terms": "Net 30",
        "remit_to_bank": "sha256:8a3c1e5d7b02",
        "confidence": "high",
        "note": "Same vendor+amount ($7,500) as historical INV-WC-2001, different inv#.",
    },
    {
        "filename": "05_tax_over_tolerance.pdf",
        "scenario": "tax_over_tolerance",
        "expected_decision": "HOLD",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Stark Logistics LLC",
        "vendor_address": "200 Grand Central, New York, NY 10017",
        "vendor_tax_id": "US-11-9988776",
        "invoice_number": "STK-7781",
        "invoice_date": "2026-08-25",
        "due_date": "2026-09-24",
        "po_number": "PO-1004",
        "currency": "USD",
        "lines": [_line("Regional freight & distribution - Q3", 1, 10300.00, tax_rate=0.0485)],
        "subtotal": 10300.00, "tax_total": 500.00, "freight": 300.00, "discount": 0.00,
        "total": 11100.00,
        "payment_terms": "Net 30",
        "remit_to_bank": "sha256:2d5b7f1a3c48",
        "confidence": "high",
        "note": "Goods subtotal $10,300 vs PO $10,000 = +3.0% over tolerance (tax/freight excluded from the check).",
    },
    {
        "filename": "06_scanned_lowconf.pdf",
        "scenario": "scanned_low_confidence",
        "expected_decision": "HOLD",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Tyrell Corporation",
        "vendor_address": "2019 Off-World Blvd, Los Angeles, CA 90013",
        "vendor_tax_id": "US-44-5566778",
        "invoice_number": "TYR-6001",
        "invoice_date": "2026-08-23",
        "due_date": "2026-09-22",
        "po_number": "PO-1009",
        "currency": "USD",
        "lines": [_line("Replicant maintenance parts", 60, 100.00)],
        "subtotal": 6000.00, "tax_total": 0.00, "freight": 0.00, "discount": 0.00,
        "total": 6000.00,
        "payment_terms": "Net 30",
        "remit_to_bank": "sha256:1f4e7a2c8d95",
        "confidence": "scanned",
        "scanned": True,
        "note": "Image-only (rasterised) PDF: no text layer -> low field confidence.",
    },
    {
        "filename": "07_po_bypass_small.pdf",
        "scenario": "po_bypass_small",
        "expected_decision": "APPROVE",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Umbrella Facilities Corp",
        "vendor_address": "13 Raccoon St, Cleveland, OH 44101",
        "vendor_tax_id": "US-90-1122334",
        "invoice_number": "UMB-0425",
        "invoice_date": "2026-08-28",
        "due_date": "2026-09-27",
        "po_number": None,
        "currency": "USD",
        "lines": [_line("Monthly janitorial service - August", 1, 420.00)],
        "subtotal": 420.00, "tax_total": 0.00, "freight": 0.00, "discount": 0.00,
        "total": 420.00,
        "payment_terms": "Net 15",
        "remit_to_bank": "sha256:7e2f4c8a9d10",
        "confidence": "high",
        "note": "No PO, <$500, approved bypass vendor (Facilities) -> APPROVE + notify.",
    },
    {
        "filename": "08_name_mismatch.pdf",
        "scenario": "vendor_name_mismatch",
        "expected_decision": "HOLD",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Acme Corp",
        "vendor_address": "500 Innovation Way, San Jose, CA 95110",
        "vendor_tax_id": "US-84-1029384",
        "invoice_number": "ACM-SUP-01",
        "invoice_date": "2026-08-26",
        "due_date": "2026-09-25",
        "po_number": "PO-1008",
        "currency": "USD",
        "lines": [_line("Extended hardware support plan (annual)", 1, 5000.00)],
        "subtotal": 5000.00, "tax_total": 0.00, "freight": 0.00, "discount": 0.00,
        "total": 5000.00,
        "payment_terms": "Net 30",
        "remit_to_bank": "sha256:9f2a1c7b0e4d",
        "confidence": "high",
        "note": "Invoice name 'Acme Corp' vs master 'Acme Corporation Inc.' -> fuzzy match.",
    },
    {
        "filename": "09_unapproved_vendor.pdf",
        "scenario": "unapproved_vendor",
        "expected_decision": "HOLD",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Ghost Supplies LLC",
        "vendor_address": "PO Box 0, Anytown, NV 89000",
        "vendor_tax_id": "US-00-0000000",
        "invoice_number": "GHS-3001",
        "invoice_date": "2026-08-27",
        "due_date": "2026-09-26",
        "po_number": "PO-1007",
        "currency": "USD",
        "lines": [_line("Miscellaneous supplies contract", 1, 3000.00)],
        "subtotal": 3000.00, "tax_total": 0.00, "freight": 0.00, "discount": 0.00,
        "total": 3000.00,
        "payment_terms": "Net 30",
        "remit_to_bank": "sha256:0000deadbeef",
        "confidence": "high",
        "note": "Vendor V008 is approved=false -> compliance HOLD (matches PO otherwise).",
    },
    {
        "filename": "10_spend_anomaly.pdf",
        "scenario": "spend_anomaly",
        "expected_decision": "HOLD",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Cyberdyne Systems Corp",
        "vendor_address": "18144 El Camino Real, Sunnyvale, CA 94087",
        "vendor_tax_id": "US-33-4455667",
        "invoice_number": "CY-9900",
        "invoice_date": "2026-08-22",
        "due_date": "2026-09-21",
        "po_number": "PO-1006",
        "currency": "USD",
        "lines": [_line("Data center server rack (fully populated)", 4, 10000.00)],
        "subtotal": 40000.00, "tax_total": 0.00, "freight": 0.00, "discount": 0.00,
        "total": 40000.00,
        "payment_terms": "Net 30",
        "remit_to_bank": "sha256:6f9d2b4a8c71",
        "confidence": "high",
        "note": "$40k vs vendor history avg ~$2,050 (~20x). Matches PO/GR but anomalous.",
    },
    {
        "filename": "11_credit_memo.pdf",
        "scenario": "credit_memo",
        "expected_decision": "HOLD",
        "doc_type": "CREDIT_MEMO",
        "title": "CREDIT MEMO",
        "vendor_name": "Soylent Foods Co",
        "vendor_address": "77 Green St, Chicago, IL 60601",
        "vendor_tax_id": "US-66-7788990",
        "invoice_number": "CM-SF-701",
        "invoice_date": "2026-08-28",
        "due_date": None,
        "po_number": "PO-1012",
        "currency": "USD",
        "lines": [_line("Catering overcharge adjustment (ref INV-SF-700)", 1, -1500.00)],
        "subtotal": -1500.00, "tax_total": 0.00, "freight": 0.00, "discount": 0.00,
        "total": -1500.00,
        "payment_terms": "Credit to account",
        "remit_to_bank": "sha256:5c2a9e7d0b13",
        "confidence": "high",
        "note": "Negative total (credit memo) -> routed separately (financial HOLD).",
    },
    {
        "filename": "12_currency_mismatch.pdf",
        "scenario": "currency_mismatch",
        "expected_decision": "HOLD",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Nakatomi Trading GmbH",
        "vendor_address": "Berliner Allee 12, 40212 Dusseldorf, Germany",
        "vendor_tax_id": "DE-811234567",
        "invoice_number": "NK-2205",
        "invoice_date": "2026-08-24",
        "due_date": "2026-09-23",
        "po_number": "PO-1005",
        "currency": "EUR",
        "lines": [_line("Imported precision components", 200, 40.00)],
        "subtotal": 8000.00, "tax_total": 0.00, "freight": 0.00, "discount": 0.00,
        "total": 8000.00,
        "payment_terms": "Net 45",
        "remit_to_bank": "sha256:3e8b6d1f9a24",
        "confidence": "high",
        "note": "Invoice currency EUR vs PO-1005 currency USD -> currency HOLD.",
    },
    {
        "filename": "13_exact_duplicate.pdf",
        "scenario": "exact_duplicate",
        "expected_decision": "REJECT",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Wayne Consulting Group",
        "vendor_address": "1007 Mountain Dr, Gotham, NY 10001",
        "vendor_tax_id": "US-55-6677889",
        "invoice_number": "INV-WC-2001",
        "invoice_date": "2026-06-15",
        "due_date": "2026-07-15",
        "po_number": "PO-1011",
        "currency": "USD",
        "lines": [_line("Q1 advisory engagement", 50, 150.00)],
        "subtotal": 7500.00, "tax_total": 0.00, "freight": 0.00, "discount": 0.00,
        "total": 7500.00,
        "payment_terms": "Net 30",
        "remit_to_bank": "sha256:8a3c1e5d7b02",
        "confidence": "high",
        "note": "Exact match of already-paid historical INV-WC-2001 (same #/amount/date).",
    },
    {
        "filename": "14_multi_gr.pdf",
        "scenario": "multi_gr_aggregation",
        "expected_decision": "APPROVE",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Hooli Cloud Services Inc.",
        "vendor_address": "900 Innovation Way, Palo Alto, CA 94301",
        "vendor_tax_id": "US-90-5551212",
        "invoice_number": "HL-2026-041",
        "invoice_date": "2026-08-27",
        "due_date": "2026-09-26",
        "po_number": "PO-1013",
        "currency": "USD",
        "lines": [_line("Managed cloud hosting - annual", 1, 10000.00)],
        "subtotal": 10000.00, "tax_total": 0.00, "freight": 0.00, "discount": 0.00,
        "total": 10000.00,
        "payment_terms": "Net 30",
        "remit_to_bank": "sha256:aa11bb22cc33",
        "confidence": "high",
        "note": "PO-1013 was received in two shipments (GR-9013a $4k + GR-9013b $6k). Invoice $10k matches the SUM; a naive matcher comparing only GR1 would wrongly flag it.",
    },
    {
        "filename": "15_awaiting_receipt.pdf",
        "scenario": "awaiting_goods_receipt",
        "expected_decision": "HOLD",
        "doc_type": "INVOICE",
        "title": "INVOICE",
        "vendor_name": "Pied Piper Data Corp",
        "vendor_address": "5230 Newell Rd, Palo Alto, CA 94303",
        "vendor_tax_id": "US-90-7773434",
        "invoice_number": "PP-2026-007",
        "invoice_date": "2026-08-27",
        "due_date": "2026-09-26",
        "po_number": "PO-1014",
        "currency": "USD",
        "lines": [_line("Data pipeline build - milestone 1", 1, 8000.00)],
        "subtotal": 8000.00, "tax_total": 0.00, "freight": 0.00, "discount": 0.00,
        "total": 8000.00,
        "payment_terms": "Net 30",
        "remit_to_bank": "sha256:dd44ee55ff66",
        "confidence": "high",
        "note": "3-way PO with NO goods receipt yet — invoice arrived before the goods. Hold awaiting receipt, not reject.",
    },
]


# ─────────────────────────── confidence profiles ───────────────────────────
def _confidence(profile: str, content: dict) -> dict[str, float]:
    fields = ["vendor_name", "invoice_number", "invoice_date", "po_number",
              "currency", "subtotal", "tax_total", "total", "line_items"]
    present = [f for f in fields if f == "line_items" or content.get(f) is not None]
    if profile == "scanned":
        # graceful degradation: OCR of a raster image -> middling/low confidence
        low = {
            "vendor_name": 0.58, "invoice_number": 0.49, "invoice_date": 0.52,
            "po_number": 0.44, "currency": 0.71, "subtotal": 0.55,
            "tax_total": 0.60, "total": 0.53, "line_items": 0.47,
        }
        return {f: low[f] for f in present}
    # high-confidence text-layer extraction
    return {f: 0.97 for f in present}


def _build_extract(content: dict) -> InvoiceExtract:
    line_items = [
        LineItem(
            description=li["description"],
            quantity=li["quantity"],
            unit_price=li["unit_price"],
            amount=li["amount"],
            tax_rate=li.get("tax_rate"),
        )
        for li in content["lines"]
    ]
    validation = {
        "line_items_sum_ok": round(sum(li["amount"] for li in content["lines"]), 2)
        == round(content["subtotal"], 2),
        "subtotal_plus_tax_ok": round(
            content["subtotal"] + content["tax_total"] + content["freight"]
            - content["discount"], 2
        ) == round(content["total"], 2),
    }
    return InvoiceExtract(
        doc_type=DocType(content["doc_type"]),
        vendor_name=content["vendor_name"],
        vendor_tax_id=content.get("vendor_tax_id"),
        vendor_address=content.get("vendor_address"),
        invoice_number=content["invoice_number"],
        invoice_date=content.get("invoice_date"),
        due_date=content.get("due_date"),
        po_number=content.get("po_number"),
        currency=content["currency"],
        line_items=line_items,
        subtotal=content["subtotal"],
        tax_total=content["tax_total"],
        freight=content["freight"],
        discount=content["discount"],
        total=content["total"],
        payment_terms=content.get("payment_terms"),
        remit_to_bank=content.get("remit_to_bank"),
        confidence=_confidence(content["confidence"], content),
        validation=validation,
    )


# ─────────────────────────── rendering: text PDF ───────────────────────────
def _money(amount: float, currency: str) -> str:
    sym = CURRENCY_SYMBOL.get(currency, currency + " ")
    if amount < 0:
        return f"-{sym}{abs(amount):,.2f}"
    return f"{sym}{amount:,.2f}"


def _invoice_text_rows(content: dict) -> list[str]:
    """Flat list of text lines describing the invoice (shared by both renderers)."""
    cur = content["currency"]
    rows = [content["title"], ""]
    rows.append(f"From: {content['vendor_name']}")
    rows.append(content["vendor_address"])
    rows.append(f"Tax ID: {content['vendor_tax_id']}")
    rows.append("")
    rows.append(f"Invoice #: {content['invoice_number']}")
    rows.append(f"Invoice Date: {content['invoice_date']}")
    if content.get("due_date"):
        rows.append(f"Due Date: {content['due_date']}")
    rows.append(f"PO Reference: {content['po_number'] or 'N/A (no PO)'}")
    rows.append(f"Currency: {cur}")
    rows.append("")
    rows.append("Description                             Qty     Unit       Amount")
    rows.append("-" * 66)
    for li in content["lines"]:
        desc = li["description"][:38].ljust(38)
        qty = f"{li['quantity']:g}".rjust(5)
        up = _money(li["unit_price"], cur).rjust(10)
        amt = _money(li["amount"], cur).rjust(12)
        rows.append(f"{desc} {qty} {up} {amt}")
    rows.append("-" * 66)
    rows.append(f"Subtotal:  {_money(content['subtotal'], cur)}")
    if content["tax_total"]:
        rows.append(f"Tax:       {_money(content['tax_total'], cur)}")
    if content["freight"]:
        rows.append(f"Freight:   {_money(content['freight'], cur)}")
    if content["discount"]:
        rows.append(f"Discount: -{_money(content['discount'], cur)}")
    rows.append(f"TOTAL:     {_money(content['total'], cur)}")
    rows.append("")
    rows.append(f"Payment Terms: {content['payment_terms']}")
    rows.append(f"Remit-to (bank ref): {content['remit_to_bank']}")
    return rows


def render_text_pdf(content: dict, path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    x = 0.9 * inch
    y = height - 0.9 * inch

    # title
    c.setFont("Helvetica-Bold", 20)
    c.drawString(x, y, content["title"])
    c.setFont("Helvetica", 9)
    c.drawRightString(width - 0.9 * inch, y, "PayFlow AP - synthetic test document")
    y -= 0.45 * inch

    # vendor block
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, content["vendor_name"]); y -= 14
    c.setFont("Helvetica", 10)
    c.drawString(x, y, content["vendor_address"]); y -= 13
    c.drawString(x, y, f"Tax ID: {content['vendor_tax_id']}"); y -= 22

    # meta block (right column)
    meta_x = width - 3.4 * inch
    my = height - 1.35 * inch
    c.setFont("Helvetica", 10)
    for label, val in [
        ("Invoice #", content["invoice_number"]),
        ("Invoice Date", content["invoice_date"]),
        ("Due Date", content.get("due_date") or "-"),
        ("PO Reference", content["po_number"] or "N/A (no PO)"),
        ("Currency", content["currency"]),
    ]:
        c.drawString(meta_x, my, f"{label}:")
        c.drawRightString(width - 0.9 * inch, my, str(val))
        my -= 14

    # line-item table
    y = min(y, my) - 6
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "Description")
    c.drawString(x + 3.6 * inch, y, "Qty")
    c.drawString(x + 4.3 * inch, y, "Unit Price")
    c.drawRightString(width - 0.9 * inch, y, "Amount")
    y -= 6
    c.line(x, y, width - 0.9 * inch, y); y -= 16
    c.setFont("Helvetica", 10)
    cur = content["currency"]
    for li in content["lines"]:
        c.drawString(x, y, li["description"][:52])
        c.drawString(x + 3.6 * inch, y, f"{li['quantity']:g}")
        c.drawString(x + 4.3 * inch, y, _money(li["unit_price"], cur))
        c.drawRightString(width - 0.9 * inch, y, _money(li["amount"], cur))
        y -= 15
    y -= 4
    c.line(x + 3.2 * inch, y, width - 0.9 * inch, y); y -= 18

    # totals
    def total_row(label, val, bold=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawString(x + 3.6 * inch, y, label)
        c.drawRightString(width - 0.9 * inch, y, _money(val, cur))
        y -= 15

    total_row("Subtotal", content["subtotal"])
    if content["tax_total"]:
        total_row("Tax", content["tax_total"])
    if content["freight"]:
        total_row("Freight", content["freight"])
    if content["discount"]:
        total_row("Discount", -content["discount"])
    total_row("TOTAL", content["total"], bold=True)

    # footer
    y -= 24
    c.setFont("Helvetica", 9)
    c.drawString(x, y, f"Payment Terms: {content['payment_terms']}"); y -= 12
    c.drawString(x, y, f"Remit-to (bank ref): {content['remit_to_bank']}")
    c.showPage()
    c.save()


# ─────────────────────────── rendering: scanned image PDF ───────────────────────────
def _load_font(size: int):
    for p in [
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def render_scanned_pdf(content: dict, path: Path) -> None:
    """Render invoice text onto a raster image, degrade it, save as image-only PDF."""
    W, H = 1275, 1650  # ~150 dpi letter
    img = Image.new("RGB", (W, H), (250, 249, 246))
    draw = ImageDraw.Draw(img)
    title_font = _load_font(46)
    mono = _load_font(26)

    draw.text((70, 60), content["title"], fill=(20, 20, 20), font=title_font)
    y = 150
    for row in _invoice_text_rows(content)[2:]:  # skip title (already drawn) + blank
        draw.text((70, y), row, fill=(30, 30, 30), font=mono)
        y += 34

    # simulate a scan: slight rotation, blur, salt-and-pepper-ish noise, grayscale
    import random
    from PIL import ImageFilter
    rnd = random.Random(1234)  # fixed seed -> deterministic bytes
    img = img.rotate(0.6, expand=False, fillcolor=(250, 249, 246))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    px = img.load()
    for _ in range(4000):
        rx, ry = rnd.randint(0, W - 1), rnd.randint(0, H - 1)
        shade = rnd.randint(150, 210)
        px[rx, ry] = (shade, shade, shade)
    img = img.convert("L").convert("RGB")

    # Embed the raster full-page via reportlab (timestamp pinned by
    # rl_config.invariant) so the scanned PDF is BOTH image-only AND
    # byte-reproducible. PIL's own PDF writer stamps a live creation date.
    import io
    from reportlab.lib.utils import ImageReader

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    c = canvas.Canvas(str(path), pagesize=letter)
    pw, ph = letter
    c.drawImage(ImageReader(buf), 0, 0, width=pw, height=ph)
    c.showPage()
    c.save()


# ─────────────────────────── driver ───────────────────────────
def _clean_dir(d: Path, pattern: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob(pattern):
        f.unlink()


def main() -> None:
    _clean_dir(INVOICES_DIR, "*.pdf")
    _clean_dir(FIXTURES_DIR, "*.json")

    manifest: list[dict] = []
    for sc in SCENARIOS:
        pdf_path = INVOICES_DIR / sc["filename"]
        if sc.get("scanned"):
            render_scanned_pdf(sc, pdf_path)
        else:
            render_text_pdf(sc, pdf_path)

        pdf_bytes = pdf_path.read_bytes()
        sha = hashlib.sha256(pdf_bytes).hexdigest()

        extract = _build_extract(sc)
        (FIXTURES_DIR / f"{sha}.json").write_text(
            json.dumps(extract.model_dump(), indent=2)
        )

        manifest.append({
            "filename": sc["filename"],
            "sha256": sha,
            "scenario": sc["scenario"],
            "expected_decision": sc["expected_decision"],
            "note": sc["note"],
        })

    (FIXTURES_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # report
    print(f"Generated {len(manifest)} invoice PDFs -> {INVOICES_DIR}")
    print(f"Wrote {len(manifest)} fixtures + manifest.json -> {FIXTURES_DIR}\n")
    print(f"{'FILE':<26}{'SCENARIO':<28}{'DECISION':<9}SHA256")
    print("-" * 100)
    for m in manifest:
        print(f"{m['filename']:<26}{m['scenario']:<28}{m['expected_decision']:<9}{m['sha256'][:16]}...")


if __name__ == "__main__":
    main()
