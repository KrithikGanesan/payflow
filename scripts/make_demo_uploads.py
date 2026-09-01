"""Generate 4 FRESH demo invoice PDFs for the live-upload demo.

Written to ~/Desktop/payflow_demo/ (NOT data/invoices/) so each has a novel
content hash → a real live Gemini extraction on upload. Values are consistent
with data/masters/* so decisions are deterministic:
  Acme  $12,000  PO-1001  -> APPROVE (3-way clean)
  Stark $10,300  PO-1004  -> HOLD    (goods 3% over PO; tax excluded)
  Cyberdyne $40,000 PO-1006-> HOLD   (20x vendor's normal spend -> anomaly)
  Umbrella $385  no PO     -> APPROVE + finance notice (PO-bypass < $500)
"""
from pathlib import Path
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

OUT = Path.home() / "Desktop" / "payflow_demo"
OUT.mkdir(parents=True, exist_ok=True)

INVOICES = [
    dict(fn="acme_ACM-2026-501.pdf", vendor="Acme Corporation Inc.",
         addr="4400 Commerce Blvd, Springfield, IL 62704", tax="US-88-1234567",
         inv="ACM-2026-501", date="2026-08-27", due="2026-09-26", po="PO-1001",
         lines=[("Enterprise Laptop 14in i7/32GB", 10, 1200.00)],
         tax_total=0.00, terms="Net 30", bank="Wells Fargo ****4021"),
    dict(fn="stark_STK-2026-880.pdf", vendor="Stark Logistics LLC",
         addr="200 Grand Central, New York, NY 10017", tax="US-11-9988776",
         inv="STK-2026-880", date="2026-08-27", due="2026-09-26", po="PO-1004",
         lines=[("Regional freight & distribution - Q3 (rate revision)", 1, 10300.00)],
         tax_total=800.00, terms="Net 30", bank="Chase ****7781"),
    dict(fn="cyberdyne_CY-2026-990.pdf", vendor="Cyberdyne Systems Corp",
         addr="18 Skynet Way, Sunnyvale, CA 94089", tax="US-77-2029384",
         inv="CY-2026-990", date="2026-08-27", due="2026-09-26", po="PO-1006",
         lines=[("Data center server rack (fully populated)", 4, 10000.00)],
         tax_total=0.00, terms="Net 30", bank="SVB ****9906"),
    dict(fn="umbrella_UMB-2026-118.pdf", vendor="Umbrella Facilities Corp",
         addr="1 Raccoon Plaza, Raccoon City, MI 48201", tax="US-55-4433221",
         inv="UMB-2026-118", date="2026-08-27", due="2026-09-26", po=None,
         lines=[("Emergency HVAC filter replacement", 1, 385.00)],
         tax_total=0.00, terms="Net 15", bank="PNC ****0425"),
    dict(fn="hooli_HL-2026-041.pdf", vendor="Hooli Cloud Services Inc.",
         addr="900 Innovation Way, Palo Alto, CA 94301", tax="US-90-5551212",
         inv="HL-2026-041", date="2026-08-27", due="2026-09-26", po="PO-1013",
         lines=[("Managed cloud hosting - annual", 1, 10000.00)],
         tax_total=0.00, terms="Net 30", bank="n/a"),
    dict(fn="piedpiper_PP-2026-007.pdf", vendor="Pied Piper Data Corp",
         addr="5230 Newell Rd, Palo Alto, CA 94303", tax="US-90-7773434",
         inv="PP-2026-007", date="2026-08-27", due="2026-09-26", po="PO-1014",
         lines=[("Data pipeline build - milestone 1", 1, 8000.00)],
         tax_total=0.00, terms="Net 30", bank="n/a"),
]

def money(x): return f"${x:,.2f}"

def draw(d):
    c = canvas.Canvas(str(OUT / d["fn"]), pagesize=LETTER)
    W, H = LETTER
    y = H - 0.9 * inch
    c.setFont("Helvetica-Bold", 20); c.drawString(0.9*inch, y, d["vendor"])
    c.setFont("Helvetica", 9); y -= 16
    c.drawString(0.9*inch, y, d["addr"]); y -= 12
    c.drawString(0.9*inch, y, f"Tax ID {d['tax']}")
    c.setFont("Helvetica-Bold", 26); c.drawRightString(W-0.9*inch, H-0.95*inch, "INVOICE")
    c.setFont("Helvetica", 10)
    ry = H - 1.35*inch
    for label, val in [("Invoice #", d["inv"]), ("Date", d["date"]), ("Due", d["due"]),
                       ("PO Number", d["po"] or "— (no PO)"), ("Terms", d["terms"])]:
        c.drawRightString(W-1.9*inch, ry, f"{label}:"); c.drawRightString(W-0.9*inch, ry, str(val)); ry -= 14
    # table
    y -= 40
    c.setFont("Helvetica-Bold", 10)
    c.drawString(0.9*inch, y, "Description"); c.drawRightString(5.2*inch, y, "Qty")
    c.drawRightString(6.4*inch, y, "Unit Price"); c.drawRightString(W-0.9*inch, y, "Amount")
    y -= 6; c.line(0.9*inch, y, W-0.9*inch, y); y -= 16
    c.setFont("Helvetica", 10); subtotal = 0.0
    for desc, qty, unit in d["lines"]:
        amt = qty*unit; subtotal += amt
        c.drawString(0.9*inch, y, desc); c.drawRightString(5.2*inch, y, str(qty))
        c.drawRightString(6.4*inch, y, money(unit)); c.drawRightString(W-0.9*inch, y, money(amt)); y -= 16
    y -= 6; c.line(4.0*inch, y, W-0.9*inch, y); y -= 18
    total = subtotal + d["tax_total"]
    for label, val, bold in [("Subtotal", subtotal, False), ("Tax", d["tax_total"], False), ("Total Due", total, True)]:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawRightString(6.4*inch, y, f"{label}:"); c.drawRightString(W-0.9*inch, y, money(val)+" USD"); y -= 16
    c.setFont("Helvetica", 8)
    c.drawString(0.9*inch, 0.8*inch, "Thank you for your business.")  # no remit-to line: avoids false bank-change flag
    c.showPage(); c.save()
    return d["fn"], total

print("Wrote to", OUT)
for d in INVOICES:
    fn, tot = draw(d); print(f"  {fn:32} total {money(tot)}")
