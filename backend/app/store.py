"""Verdict persistence layer — SQLite (stdlib sqlite3).

Owns the durable state of the AP system: master data (vendors, POs, goods
receipts, historical invoices) plus the append-only record of runs, stages and
notifications produced by the orchestrator.

Contracts models are serialized to/from JSON text columns — the model is the
source of truth for shape, the DB just stores it. No business logic lives here;
this module is pure I/O.

DB path comes from env ``DB_PATH`` (default ``verdict.db`` in the cwd).
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

from .contracts import (
    DecisionResult,
    GoodsReceipt,
    HistoricalInvoice,
    InvoiceExtract,
    Notification,
    PurchaseOrder,
    RunRecord,
    StageResult,
    Vendor,
)

# Repo root = .../verdict ; this file is backend/app/store.py
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MASTERS_DIR = _REPO_ROOT / "data" / "masters"


def db_path() -> str:
    """Resolved DB path (env DB_PATH or default 'verdict.db')."""
    return os.environ.get("DB_PATH", "verdict.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─────────────────────────── schema ───────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS vendor_master (
    vendor_id   TEXT PRIMARY KEY,
    legal_name  TEXT NOT NULL,
    approved    INTEGER NOT NULL,
    data        TEXT NOT NULL          -- Vendor JSON
);

CREATE TABLE IF NOT EXISTS po_master (
    po_number         TEXT PRIMARY KEY,
    vendor_id         TEXT NOT NULL,
    cumulative_billed REAL NOT NULL DEFAULT 0,
    data              TEXT NOT NULL     -- PurchaseOrder JSON
);

CREATE TABLE IF NOT EXISTS goods_receipts (
    gr_id       TEXT PRIMARY KEY,
    po_number   TEXT NOT NULL,
    data        TEXT NOT NULL           -- GoodsReceipt JSON
);

CREATE TABLE IF NOT EXISTS historical_invoices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id       TEXT NOT NULL,
    invoice_number  TEXT NOT NULL,
    amount          REAL NOT NULL,
    invoice_date    TEXT NOT NULL,
    data            TEXT NOT NULL,      -- HistoricalInvoice JSON
    UNIQUE(vendor_id, invoice_number)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    invoice_file  TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    cycle_time_ms INTEGER NOT NULL DEFAULT 0,
    actor         TEXT NOT NULL DEFAULT 'ai',
    decision      TEXT,                 -- denormalized for quick listing
    extract       TEXT,                 -- InvoiceExtract JSON
    result        TEXT,                 -- DecisionResult JSON
    data          TEXT NOT NULL         -- full RunRecord JSON
);

CREATE TABLE IF NOT EXISTS run_stages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    stage       TEXT NOT NULL,
    status      TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    output      TEXT NOT NULL,          -- StageResult.output JSON
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT,
    type        TEXT NOT NULL,
    recipient   TEXT NOT NULL,
    message     TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS ix_hist_vendor ON historical_invoices(vendor_id);
CREATE INDEX IF NOT EXISTS ix_stages_run  ON run_stages(run_id);
CREATE INDEX IF NOT EXISTS ix_notif_run   ON notifications(run_id);
CREATE INDEX IF NOT EXISTS ix_po_vendor   ON po_master(vendor_id);
"""


def init_db() -> None:
    """Create all tables/indexes if they do not exist. Idempotent."""
    with _connect() as conn:
        conn.executescript(_SCHEMA)


# ─────────────────────────── masters load ───────────────────────────
def load_masters(masters_dir: Optional[str | Path] = None) -> dict[str, int]:
    """Load the four master JSON files into the DB (INSERT OR REPLACE).

    Reads ``vendors.json``, ``purchase_orders.json``, ``goods_receipts.json``,
    ``historical_invoices.json`` from ``masters_dir`` (default data/masters).
    Idempotent — safe to re-run. Returns per-table row counts inserted.
    """
    base = Path(masters_dir) if masters_dir else _DEFAULT_MASTERS_DIR
    counts: dict[str, int] = {}

    def _load(name: str) -> list:
        p = base / name
        if not p.exists():
            return []
        return json.loads(p.read_text())

    vendors = [Vendor.model_validate(v) for v in _load("vendors.json")]
    pos = [PurchaseOrder.model_validate(p) for p in _load("purchase_orders.json")]
    grs = [GoodsReceipt.model_validate(g) for g in _load("goods_receipts.json")]
    hist = [HistoricalInvoice.model_validate(h) for h in _load("historical_invoices.json")]

    with _connect() as conn:
        for v in vendors:
            conn.execute(
                "INSERT OR REPLACE INTO vendor_master(vendor_id, legal_name, approved, data)"
                " VALUES (?,?,?,?)",
                (v.vendor_id, v.legal_name, int(v.approved), v.model_dump_json()),
            )
        for p in pos:
            conn.execute(
                "INSERT OR REPLACE INTO po_master(po_number, vendor_id, cumulative_billed, data)"
                " VALUES (?,?,?,?)",
                (p.po_number, p.vendor_id, p.cumulative_billed, p.model_dump_json()),
            )
        for g in grs:
            conn.execute(
                "INSERT OR REPLACE INTO goods_receipts(gr_id, po_number, data) VALUES (?,?,?)",
                (g.gr_id, g.po_number, g.model_dump_json()),
            )
        for h in hist:
            conn.execute(
                "INSERT OR REPLACE INTO historical_invoices"
                "(vendor_id, invoice_number, amount, invoice_date, data) VALUES (?,?,?,?,?)",
                (h.vendor_id, h.invoice_number, h.amount, h.invoice_date, h.model_dump_json()),
            )

    counts["vendor_master"] = len(vendors)
    counts["po_master"] = len(pos)
    counts["goods_receipts"] = len(grs)
    counts["historical_invoices"] = len(hist)
    return counts


# ─────────────────────────── vendors ───────────────────────────
def get_vendor(vendor_id: str) -> Optional[Vendor]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT data FROM vendor_master WHERE vendor_id = ?", (vendor_id,)
        ).fetchone()
    return Vendor.model_validate_json(row["data"]) if row else None


def list_vendors() -> list[Vendor]:
    with _connect() as conn:
        rows = conn.execute("SELECT data FROM vendor_master ORDER BY vendor_id").fetchall()
    return [Vendor.model_validate_json(r["data"]) for r in rows]


# ─────────────────────────── purchase orders ───────────────────────────
def get_po(po_number: str) -> Optional[PurchaseOrder]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT data FROM po_master WHERE po_number = ?", (po_number,)
        ).fetchone()
    return PurchaseOrder.model_validate_json(row["data"]) if row else None


def update_cumulative_billed(po_number: str, add_amount: float) -> Optional[PurchaseOrder]:
    """Add ``add_amount`` to a PO's cumulative_billed (split/partial billing).

    Persists the new value into both the mirror column and the stored PO JSON.
    Returns the updated PurchaseOrder, or None if the PO is unknown.
    """
    po = get_po(po_number)
    if po is None:
        return None
    po.cumulative_billed = round(po.cumulative_billed + add_amount, 2)
    with _connect() as conn:
        conn.execute(
            "UPDATE po_master SET cumulative_billed = ?, data = ? WHERE po_number = ?",
            (po.cumulative_billed, po.model_dump_json(), po_number),
        )
    return po


# ─────────────────────────── goods receipts ───────────────────────────
def get_goods_receipt(po_number: str) -> Optional[GoodsReceipt]:
    """Most recent goods receipt for a PO (3-way match), or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT data FROM goods_receipts WHERE po_number = ? ORDER BY gr_id DESC LIMIT 1",
            (po_number,),
        ).fetchone()
    return GoodsReceipt.model_validate_json(row["data"]) if row else None


def goods_receipts_for(po_number: str) -> list[GoodsReceipt]:
    """ALL goods receipts for a PO — 3-way matching sums across receipts."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT data FROM goods_receipts WHERE po_number = ? ORDER BY gr_id",
            (po_number,),
        ).fetchall()
    return [GoodsReceipt.model_validate_json(r["data"]) for r in rows]


# ─────────────────────────── historical invoices ───────────────────────────
def historical_invoices_for(vendor_id: str) -> list[HistoricalInvoice]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT data FROM historical_invoices WHERE vendor_id = ? ORDER BY invoice_date",
            (vendor_id,),
        ).fetchall()
    return [HistoricalInvoice.model_validate_json(r["data"]) for r in rows]


# ─────────────────────────── runs ───────────────────────────
def save_run(run: RunRecord) -> None:
    """Upsert a RunRecord and its stages (stages replaced wholesale)."""
    decision = run.result.decision.value if run.result else None
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs"
            "(run_id, invoice_file, created_at, cycle_time_ms, actor, decision, extract, result, data)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                run.run_id,
                run.invoice_file,
                run.created_at,
                run.cycle_time_ms,
                run.actor,
                decision,
                run.extract.model_dump_json() if run.extract else None,
                run.result.model_dump_json() if run.result else None,
                run.model_dump_json(),
            ),
        )
        # replace stages so re-saving a run is idempotent
        conn.execute("DELETE FROM run_stages WHERE run_id = ?", (run.run_id,))
        for st in run.stages:
            conn.execute(
                "INSERT INTO run_stages(run_id, stage, status, duration_ms, output)"
                " VALUES (?,?,?,?,?)",
                (run.run_id, st.stage.value, st.status, st.duration_ms, json.dumps(st.output)),
            )


def save_stage(run_id: str, stage: StageResult) -> None:
    """Append a single stage result (used when streaming stage-by-stage)."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO run_stages(run_id, stage, status, duration_ms, output) VALUES (?,?,?,?,?)",
            (run_id, stage.stage.value, stage.status, stage.duration_ms, json.dumps(stage.output)),
        )


def save_notification(notification: Notification, run_id: Optional[str] = None) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO notifications(run_id, type, recipient, message) VALUES (?,?,?,?)",
            (run_id, notification.type, notification.recipient, notification.message),
        )


def list_runs() -> list[RunRecord]:
    """All runs, newest first (by created_at)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT data FROM runs ORDER BY created_at DESC, run_id DESC"
        ).fetchall()
    return [RunRecord.model_validate_json(r["data"]) for r in rows]


def get_run(run_id: str) -> Optional[RunRecord]:
    with _connect() as conn:
        row = conn.execute("SELECT data FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return RunRecord.model_validate_json(row["data"]) if row else None


def list_notifications(run_id: Optional[str] = None) -> list[Notification]:
    with _connect() as conn:
        if run_id:
            rows = conn.execute(
                "SELECT type, recipient, message FROM notifications WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT type, recipient, message FROM notifications ORDER BY id"
            ).fetchall()
    return [
        Notification(type=r["type"], recipient=r["recipient"], message=r["message"]) for r in rows
    ]
