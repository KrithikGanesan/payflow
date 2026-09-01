"""Ollama extraction provider — local, offline LLM fallback.

Talks to a local Ollama server (default http://localhost:11434) over plain
urllib (no extra dependency). Feeds the pdfplumber text layer to a local model
and reuses the shared schema prompt + JSON parser from ``gemini``.

Text-layer only by design: rendering PDF pages to images for a local vision
model is heavier than this layer needs. Machine-readable PDFs extract well;
scanned PDFs are better served by the Gemini provider. Import-safe with no
server running — only ``extract()`` reaches out.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .gemini import build_prompt, extract_text_layer, parse_invoice_json

try:
    from ..contracts import InvoiceExtract
except ImportError:  # pragma: no cover
    from app.contracts import InvoiceExtract  # type: ignore


DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"


class OllamaProvider:
    """ExtractionProvider backed by a local Ollama server."""

    def __init__(self, model: str | None = None, host: str | None = None):
        self.model_name = model or os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
        self.host = (host or os.getenv("OLLAMA_HOST", DEFAULT_HOST)).rstrip("/")

    def extract(self, pdf_path: str) -> InvoiceExtract:
        text_layer = extract_text_layer(pdf_path)
        if not text_layer:
            raise RuntimeError(
                "Ollama provider needs a PDF text layer; this PDF appears "
                "scanned. Use EXTRACTION_PROVIDER=gemini for scanned documents."
            )
        prompt = build_prompt(text_layer)

        payload = json.dumps(
            {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0},
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {self.host}: {exc}. "
                "Is `ollama serve` running?"
            ) from exc

        return parse_invoice_json(body.get("response", ""))
