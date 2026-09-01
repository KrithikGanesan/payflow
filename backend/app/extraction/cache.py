"""Content-addressed cache for extraction output.

Extraction is cached by the sha256 of the source PDF bytes. This makes live
runs deterministic on replay (same PDF -> same JSON) and lets the app run with
no API key at all (the `fixture` provider reads the very same files).

Cache files live in ``data/fixtures/<sha256>.json``. Writing is gated on the
``EXTRACTION_CACHE=1`` env var and is *append-only*: a hand-authored
ground-truth fixture is never overwritten.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

try:  # normal case: imported as app.extraction.cache
    from ..contracts import InvoiceExtract
except ImportError:  # pragma: no cover - allow flat import (cwd == backend/app)
    from app.contracts import InvoiceExtract  # type: ignore


# repo root = <root>/backend/app/extraction/cache.py -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = _REPO_ROOT / "data"
FIXTURES_DIR = DATA_DIR / "fixtures"


def sha256_bytes(data: bytes) -> str:
    """Hex sha256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_of_pdf(pdf_path: str) -> str:
    """Hex sha256 of a file's bytes (used as the cache/fixture key)."""
    with open(pdf_path, "rb") as fh:
        return sha256_bytes(fh.read())


def fixture_path(sha: str) -> Path:
    """Absolute path of the fixture/cache file for a given hash."""
    return FIXTURES_DIR / f"{sha}.json"


def cache_enabled() -> bool:
    """True if EXTRACTION_CACHE is set to a truthy value."""
    return os.getenv("EXTRACTION_CACHE", "0").strip().lower() in {"1", "true", "yes", "on"}


def cache_read(sha: str) -> Optional[InvoiceExtract]:
    """Return the cached/ground-truth extract for a hash, or None if absent.

    Reading is always allowed (independent of EXTRACTION_CACHE) so that
    hand-authored fixtures and prior cached runs are honoured for deterministic
    replay. A corrupt file returns None rather than raising, so a bad cache
    entry degrades to a fresh extraction instead of crashing the pipeline.
    """
    path = fixture_path(sha)
    if not path.exists():
        return None
    try:
        return InvoiceExtract.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def cache_write(extract: InvoiceExtract, sha: str) -> Optional[Path]:
    """Persist an extract to the fixture cache. Returns the path if written.

    No-op when EXTRACTION_CACHE is disabled or when a file for this hash
    already exists (never clobber a ground-truth fixture / prior cache entry).
    """
    if not cache_enabled():
        return None
    path = fixture_path(sha)
    if path.exists():
        return None
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        extract.model_dump_json(indent=2, exclude_none=False),
        encoding="utf-8",
    )
    return path
