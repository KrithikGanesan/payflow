"""Verdict extraction layer.

Public API:
    extract(pdf_path) -> InvoiceExtract   # cache -> provider -> validate -> cache
    get_provider(name=None)               # ExtractionProvider factory
    validate(extract)                     # arithmetic + format + confidence
    sha256_of_pdf(path)                   # content-address helper
"""
from .cache import sha256_bytes, sha256_of_pdf
from .interface import ExtractionProvider, extract, get_provider
from .validate import validate

__all__ = [
    "extract",
    "get_provider",
    "ExtractionProvider",
    "validate",
    "sha256_of_pdf",
    "sha256_bytes",
]
