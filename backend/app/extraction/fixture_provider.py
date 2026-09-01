"""Fixture extraction provider — key-free, fully deterministic.

Keys extraction by the sha256 of the PDF bytes and reads the corresponding
``data/fixtures/<sha256>.json`` (the same location the cache writes to). This
lets the entire app run with no API key: hand-authored ground-truth fixtures
and previously cached live runs are both honoured.

Raises a clear error when no fixture exists for a PDF so the failure is
actionable rather than a mysterious empty result.
"""
from __future__ import annotations

from .cache import cache_read, fixture_path, sha256_of_pdf

try:
    from ..contracts import InvoiceExtract
except ImportError:  # pragma: no cover
    from app.contracts import InvoiceExtract  # type: ignore


class FixtureProvider:
    """ExtractionProvider that replays a stored fixture for the PDF."""

    def extract(self, pdf_path: str) -> InvoiceExtract:
        sha = sha256_of_pdf(pdf_path)
        cached = cache_read(sha)
        if cached is None:
            raise FileNotFoundError(
                f"No fixture for {pdf_path} (sha256={sha}). "
                f"Expected: {fixture_path(sha)}. "
                "Generate it with a live provider + EXTRACTION_CACHE=1, or "
                "hand-author the ground-truth JSON."
            )
        return cached
