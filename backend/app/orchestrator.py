"""Verdict pipeline orchestrator.

Wires the three lower layers into a staged pipeline WITHOUT reimplementing their
logic: extraction.extract (source of truth for fields) -> engine.decide (source of
truth for the verdict + precedence). We call decide() ONCE and decompose its result
across the CODED/MATCHED/VALIDATED/DECIDED stages purely for the live view.

Two entry points share the same core:
  - process(run_id, invoice_file)      -> RunRecord   (synchronous; used by wait/seed/smoke)
  - stream(run_id, invoice_file)       -> AsyncIterator[SSEEvent]  (live, with per-stage delays)
Both persist the final RunRecord + notifications via the store.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Optional

from . import extraction, store
from .contracts import (
    DecisionResult,
    GoodsReceipt,
    InvoiceExtract,
    RunRecord,
    SSEEvent,
    Stage,
    StageResult,
)
from .engine import decide as engine_decide

REPO = Path(__file__).resolve().parents[2]  # …/verdict
INVOICES = REPO / "data" / "invoices"
UPLOADS = REPO / "data" / "uploads"
STAGE_DELAY_MS = int(os.getenv("STAGE_DELAY_MS", "350"))

_STAGE_ORDER = [Stage.RECEIVED, Stage.EXTRACTED, Stage.CODED, Stage.MATCHED, Stage.VALIDATED, Stage.DECIDED]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_pdf(invoice_file: str) -> Path:
    """Accept a bare corpus filename, an upload name, or an explicit path."""
    p = Path(invoice_file)
    if p.is_absolute() and p.exists():
        return p
    for base in (INVOICES, UPLOADS, REPO):
        cand = base / p.name
        if cand.exists():
            return cand
    raise FileNotFoundError(f"invoice not found: {invoice_file}")


def default_invoice() -> Optional[str]:
    pdfs = sorted(INVOICES.glob("*.pdf"))
    return pdfs[0].name if pdfs else None


def _gather_masters(extract: InvoiceExtract):
    vendors = store.list_vendors()
    po = store.get_po(extract.po_number) if extract.po_number else None
    gr = None
    if po:
        grs = store.goods_receipts_for(po.po_number)
        if grs:  # sum receipts so split deliveries match a single invoice (3-way)
            total = round(sum(g.received_total for g in grs), 2)
            label = grs[0].gr_id if len(grs) == 1 else f"{len(grs)} receipts"
            gr = GoodsReceipt(gr_id=label, po_number=po.po_number, received_total=total,
                              received_date=max(g.received_date for g in grs))
    historical = []
    for v in vendors:
        historical += store.historical_invoices_for(v.vendor_id)
    return vendors, po, gr, historical


# ── per-stage output decomposition (from the single decide() result) ──
def _stage_output(stage: Stage, pdf_name: str, extract: Optional[InvoiceExtract], result: Optional[DecisionResult]) -> dict:
    if stage is Stage.RECEIVED:
        return {"file": pdf_name}
    if stage is Stage.EXTRACTED and extract is not None:
        return {
            "vendor_name": extract.vendor_name,
            "invoice_number": extract.invoice_number,
            "po_number": extract.po_number,
            "currency": extract.currency,
            "total": extract.total,
            "doc_type": extract.doc_type.value if extract.doc_type else None,
            "confidence": extract.confidence.get("_overall"),
        }
    if result is None:
        return {}
    if stage is Stage.CODED:
        gl = result.gl_coding
        return {"account": gl.account, "cost_center": gl.cost_center, "confidence": gl.confidence} if gl else {}
    if stage is Stage.MATCHED:
        return {"matched_po": result.matched_po, "cumulative_after": result.cumulative_after}
    if stage is Stage.VALIDATED:
        return {"flags": [
            {"code": r.code.value, "severity": r.severity.value, "message": r.message}
            for r in result.reasons if r.severity.value != "INFO"
        ]}
    if stage is Stage.DECIDED:
        return {
            "decision": result.decision.value,
            "routed_to": result.routed_to,
            "materiality_band": result.materiality_band,
            "reasons": [{"code": r.code.value, "severity": r.severity.value, "message": r.message, "rule": r.rule, "values": r.values} for r in result.reasons],
            "notifications": [n.model_dump() for n in result.notifications],
        }
    return {}


def _persist(run: RunRecord, result: Optional[DecisionResult]) -> None:
    store.save_run(run)
    if result:
        for n in result.notifications:
            store.save_notification(n, run_id=run.run_id)


# ── synchronous core (no delays, no events) ──
def process(run_id: str, invoice_file: str) -> RunRecord:
    t0 = time.time()
    pdf = resolve_pdf(invoice_file)
    extract = extraction.extract(str(pdf))
    vendors, po, gr, historical = _gather_masters(extract)
    result = engine_decide.decide(extract, vendors, po, gr, historical)
    stages = [
        StageResult(stage=s, status="ok", duration_ms=0, output=_stage_output(s, pdf.name, extract, result))
        for s in _STAGE_ORDER
    ]
    run = RunRecord(
        run_id=run_id, invoice_file=pdf.name, created_at=_now(),
        extract=extract, result=result, stages=stages,
        cycle_time_ms=int((time.time() - t0) * 1000), actor="ai",
    )
    _persist(run, result)
    return run


# ── async streaming pipeline (live view) ──
async def stream(run_id: str, invoice_file: str) -> AsyncIterator[SSEEvent]:
    t0 = time.time()
    pdf = resolve_pdf(invoice_file)
    extract: Optional[InvoiceExtract] = None
    result: Optional[DecisionResult] = None
    stages: list[StageResult] = []

    def ev(etype: str, stage: Optional[Stage] = None, status: Optional[str] = None, payload: Optional[dict] = None) -> SSEEvent:
        return SSEEvent(type=etype, run_id=run_id, stage=stage, status=status, payload=payload or {}, ts=_now())

    try:
        for stage in _STAGE_ORDER:
            yield ev("stage_started", stage, "running")
            s0 = time.time()
            # compute the work that becomes visible at each stage
            if stage is Stage.EXTRACTED:
                extract = extraction.extract(str(pdf))
            elif stage is Stage.CODED:
                # first stage after extraction → run the full decision once
                vendors, po, gr, historical = _gather_masters(extract)
                result = engine_decide.decide(extract, vendors, po, gr, historical)
            await asyncio.sleep(STAGE_DELAY_MS / 1000)
            out = _stage_output(stage, pdf.name, extract, result)
            sr = StageResult(stage=stage, status="ok", duration_ms=int((time.time() - s0) * 1000), output=out)
            stages.append(sr)
            yield ev("stage_completed", stage, "ok", out)
    except Exception as exc:  # surface a failed stage instead of a silent hang
        yield ev("stage_completed", None, "fail", {"error": str(exc)})
        raise

    run = RunRecord(
        run_id=run_id, invoice_file=pdf.name, created_at=_now(),
        extract=extract, result=result, stages=stages,
        cycle_time_ms=int((time.time() - t0) * 1000), actor="ai",
    )
    _persist(run, result)
    yield ev("run_completed", Stage.DECIDED, result.decision.value if result else None,
             {"decision": result.decision.value if result else None})
