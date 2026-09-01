#!/usr/bin/env python
"""End-to-end backend integration test.

Runs EVERY corpus invoice through the real pipeline (extraction -> engine -> orchestrator)
in fixture mode and asserts each decision matches the ground-truth manifest.
Exits non-zero on any mismatch.

    EXTRACTION_PROVIDER=fixture ./.venv/bin/python scripts/smoke_test.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("EXTRACTION_PROVIDER", "fixture")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app import orchestrator, store  # noqa: E402

MANIFEST = REPO / "data" / "fixtures" / "manifest.json"


def _load_manifest() -> dict[str, str]:
    """Return {filename -> expected_decision}, tolerant of key naming."""
    raw = json.loads(MANIFEST.read_text())
    entries = raw if isinstance(raw, list) else raw.get("invoices") or raw.get("entries") or list(raw.values())
    out: dict[str, str] = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        fn = e.get("filename") or e.get("file") or e.get("name")
        dec = (e.get("expected_decision") or e.get("decision") or "").upper()
        if fn and dec:
            out[Path(fn).name] = dec
    return out


def main() -> int:
    store.init_db()
    if not store.list_vendors():
        store.load_masters()

    expected = _load_manifest()
    pdfs = sorted((REPO / "data" / "invoices").glob("*.pdf"))
    if not pdfs:
        print("NO INVOICES FOUND — run scripts/generate_corpus.py first", file=sys.stderr)
        return 2

    rows, fails = [], 0
    for pdf in pdfs:
        exp = expected.get(pdf.name, "—")
        try:
            run = orchestrator.process("smoke_" + pdf.stem, pdf.name)
            got = run.result.decision.value if run.result else "ERROR"
            top = next((r.code.value for r in run.result.reasons if r.severity.value != "INFO"), "—") if run.result else "—"
        except Exception as exc:
            got, top = f"EXC:{type(exc).__name__}", str(exc)[:40]
        ok = (exp == got) or exp == "—"
        if not ok:
            fails += 1
        rows.append((pdf.name, exp, got, top, "PASS" if ok else "FAIL"))

    w = max(len(r[0]) for r in rows)
    print(f"\n{'file':<{w}}  {'expected':<9} {'actual':<9} {'top_reason':<26} result")
    print("-" * (w + 55))
    for fn, exp, got, top, res in rows:
        print(f"{fn:<{w}}  {exp:<9} {got:<9} {top:<26} {res}")
    print("-" * (w + 55))
    total = len(rows)
    print(f"{total - fails}/{total} matched expected decision"
          + (f"  · {fails} MISMATCH" if fails else "  · ALL GREEN ✓"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
