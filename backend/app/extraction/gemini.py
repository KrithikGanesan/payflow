"""Gemini extraction provider (default).

Sends the PDF two ways at once for maximum accuracy:
  * the raw PDF bytes inline (Gemini reads layout + OCRs scanned pages), and
  * the pdfplumber-extracted text layer (exact glyphs on machine-readable PDFs,
    so the model transcribes rather than guesses digits).

The prompt pins the exact ``InvoiceExtract`` JSON schema, forces doc-type
detection, demands ``null`` for anything not present ("never guess"), and asks
for a per-field confidence map.

Import-safe with no key: ``google.generativeai`` imports fine and the provider
constructs fine; only the actual API call in ``extract()`` requires
``GEMINI_API_KEY``.

The prompt/parse/text-layer helpers are reused by the Ollama provider.
"""
from __future__ import annotations

import json
import os
from typing import Optional

import google.generativeai as genai
import pdfplumber

try:
    from ..contracts import InvoiceExtract, LineItem, DocType
except ImportError:  # pragma: no cover
    from app.contracts import InvoiceExtract, LineItem, DocType  # type: ignore


DEFAULT_MODEL = "gemini-2.0-flash"

# Exact schema the model must emit. Kept in lockstep with contracts.InvoiceExtract.
SCHEMA_PROMPT = """You are an expert accounts-payable document extractor. Extract structured data from the supplied vendor document.

Return ONE JSON object and NOTHING else. It MUST match this schema exactly:

{
  "doc_type": "INVOICE" | "CREDIT_MEMO" | "STATEMENT" | "OTHER",
  "vendor_name": string | null,
  "vendor_tax_id": string | null,
  "vendor_address": string | null,
  "invoice_number": string | null,
  "invoice_date": string | null,        // ISO 8601, YYYY-MM-DD
  "due_date": string | null,            // ISO 8601, YYYY-MM-DD
  "po_number": string | null,
  "currency": string | null,            // ISO 4217, e.g. "USD"
  "line_items": [
    {
      "description": string,
      "quantity": number | null,
      "unit_price": number | null,
      "amount": number | null,
      "tax_rate": number | null         // decimal fraction, e.g. 0.08 for 8%
    }
  ],
  "subtotal": number | null,
  "tax_total": number | null,
  "freight": number | null,
  "discount": number | null,
  "total": number | null,
  "payment_terms": string | null,       // e.g. "2/10 net 30"
  "remit_to_bank": string | null,       // bank account / IBAN / routing if shown
  "confidence": { "<field_name>": number }   // 0..1 per field you filled
}

RULES — read carefully:
- doc_type: CREDIT_MEMO if it is a negative/credit invoice; STATEMENT if it is an
  account statement listing multiple invoices; OTHER if it is not an AP document
  (e.g. a letter, receipt, catalog); otherwise INVOICE.
- NEVER GUESS. If a field is not clearly present, return null (or [] for line_items).
  Do not invent invoice numbers, dates, tax IDs, or totals.
- Numbers must be raw numbers: no currency symbols, no thousands separators.
- Credit memos: represent credited amounts as NEGATIVE numbers.
- tax_rate is a decimal fraction (8% -> 0.08), never a percentage integer.
- confidence: for every field you populated, include a key with your 0..1
  confidence for that specific value (1 = certain, 0 = pure guess). Lower your
  confidence for anything faint, handwritten, or ambiguous.
- Prefer the exact digits in the provided TEXT LAYER when it and the image
  disagree on a machine-readable page.
"""


def extract_text_layer(pdf_path: str) -> str:
    """Best-effort pdfplumber text extraction. Empty string for scanned PDFs."""
    try:
        parts: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                if txt.strip():
                    parts.append(txt)
        return "\n\n".join(parts).strip()
    except Exception:
        return ""


def build_prompt(text_layer: str) -> str:
    """Schema prompt plus the extracted text layer (if any)."""
    if text_layer:
        return (
            SCHEMA_PROMPT
            + "\n\n--- EXTRACTED TEXT LAYER (authoritative for exact digits) ---\n"
            + text_layer
        )
    return (
        SCHEMA_PROMPT
        + "\n\n--- NOTE: no text layer (scanned/image PDF). Read the image and OCR it. ---"
    )


def _strip_json(raw: str) -> str:
    """Pull the JSON object out of a model response (fences, prose, etc.)."""
    s = raw.strip()
    if s.startswith("```"):
        # remove ```json ... ``` fences
        s = s.split("```", 2)
        s = s[1] if len(s) > 1 else raw
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1]
    return s.strip()


def parse_invoice_json(raw: str) -> InvoiceExtract:
    """Parse a raw model response into an InvoiceExtract, defensively."""
    data = json.loads(_strip_json(raw))
    if not isinstance(data, dict):
        raise ValueError("model did not return a JSON object")

    # Normalize doc_type to the enum (unknown -> OTHER).
    dt = str(data.get("doc_type", "INVOICE") or "INVOICE").upper()
    data["doc_type"] = dt if dt in DocType.__members__ else DocType.OTHER.value

    # Coerce line_items defensively.
    items = data.get("line_items") or []
    clean_items: list[LineItem] = []
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                clean_items.append(
                    LineItem(
                        description=str(it.get("description") or ""),
                        quantity=it.get("quantity"),
                        unit_price=it.get("unit_price"),
                        amount=it.get("amount"),
                        tax_rate=it.get("tax_rate"),
                    )
                )
    data["line_items"] = clean_items

    # Confidence must be a {str: float} map.
    conf = data.get("confidence")
    if isinstance(conf, dict):
        data["confidence"] = {
            str(k): float(v)
            for k, v in conf.items()
            if isinstance(v, (int, float))
        }
    else:
        data["confidence"] = {}

    data.pop("validation", None)  # never trust a provider-supplied validation map
    return InvoiceExtract.model_validate(data)


class GeminiProvider:
    """ExtractionProvider backed by Google Gemini."""

    def __init__(self, model: Optional[str] = None):
        # Constructing must never require the key.
        self.model_name = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self.api_key = os.getenv("GEMINI_API_KEY")

    def extract(self, pdf_path: str) -> InvoiceExtract:
        if not self.api_key or self.api_key.startswith("paste-"):
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Set it, or run with "
                "EXTRACTION_PROVIDER=fixture for key-free operation."
            )
        genai.configure(api_key=self.api_key)

        with open(pdf_path, "rb") as fh:
            pdf_bytes = fh.read()
        text_layer = extract_text_layer(pdf_path)
        prompt = build_prompt(text_layer)

        model = genai.GenerativeModel(self.model_name)
        response = model.generate_content(
            [
                prompt,
                {"mime_type": "application/pdf", "data": pdf_bytes},
            ],
            generation_config={
                "temperature": 0.0,
                "response_mime_type": "application/json",
            },
        )
        return parse_invoice_json(response.text)
