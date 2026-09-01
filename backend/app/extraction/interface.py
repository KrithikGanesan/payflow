"""Extraction interface: provider protocol, factory, and the public entrypoint.

``extract(pdf_path)`` is what the rest of the app calls. It:
  1. hashes the PDF and checks the cache/fixture store,
  2. otherwise runs the configured provider,
  3. runs validation (arithmetic + format + confidence calibration),
  4. writes the result back to the cache (when EXTRACTION_CACHE=1),
and returns a validated ``InvoiceExtract``.

Provider is chosen by ``EXTRACTION_PROVIDER`` (gemini | ollama | fixture),
defaulting to gemini.
"""
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from . import cache
from .validate import validate

try:
    from ..contracts import InvoiceExtract
except ImportError:  # pragma: no cover
    from app.contracts import InvoiceExtract  # type: ignore


@runtime_checkable
class ExtractionProvider(Protocol):
    """Anything that turns a PDF path into an InvoiceExtract."""

    def extract(self, pdf_path: str) -> InvoiceExtract:  # pragma: no cover - protocol
        ...


def get_provider(name: str | None = None) -> ExtractionProvider:
    """Return a provider instance for ``name`` or the EXTRACTION_PROVIDER env.

    Providers are imported lazily so that, e.g., selecting `fixture` never
    imports google-generativeai and selecting `gemini` never needs Ollama.
    """
    provider = (name or os.getenv("EXTRACTION_PROVIDER", "gemini")).strip().lower()

    if provider == "fixture":
        from .fixture_provider import FixtureProvider
        return FixtureProvider()
    if provider == "ollama":
        from .ollama import OllamaProvider
        return OllamaProvider()
    if provider == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider()

    raise ValueError(
        f"Unknown EXTRACTION_PROVIDER={provider!r} "
        "(expected one of: gemini, ollama, fixture)"
    )


def extract(pdf_path: str) -> InvoiceExtract:
    """Public entrypoint: cache -> provider -> validate -> cache."""
    sha = cache.sha256_of_pdf(pdf_path)

    cached = cache.cache_read(sha)
    if cached is not None:
        # Deterministic replay. Re-run validation (idempotent) so validation
        # flags and the overall-confidence signal are always populated, even
        # for hand-authored fixtures.
        return validate(cached)

    result = get_provider().extract(pdf_path)
    result = validate(result)
    cache.cache_write(result, sha)
    return result
