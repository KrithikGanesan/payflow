#!/usr/bin/env python
"""Seed the Verdict database: init schema + load master data, then print counts.

Run:  ./.venv/bin/python scripts/seed.py
DB path honours env DB_PATH (default verdict.db in the cwd).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app import store  # noqa: E402


def main() -> None:
    store.init_db()
    counts = store.load_masters()

    print(f"Database ready at: {store.db_path()}")
    print("Master data loaded:")
    for table, n in counts.items():
        print(f"  {table:<22} {n:>4} rows")

    # quick integrity summary
    vendors = store.list_vendors()
    approved = sum(1 for v in vendors if v.approved)
    bypass = sum(1 for v in vendors if v.po_bypass_allowed)
    print("\nVendor summary:")
    print(f"  approved              {approved:>4} / {len(vendors)}")
    print(f"  po_bypass_allowed     {bypass:>4}")


if __name__ == "__main__":
    main()
