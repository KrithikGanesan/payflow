"""PayFlow FastAPI backend. Routes live at root; the Vite dev proxy strips /api.

  GET  /health
  GET  /runs                 -> list[RunRecord]
  GET  /runs/{id}            -> RunRecord
  POST /runs {invoice_file}  -> {run_id}   (?wait=1 -> full RunRecord)
  GET  /runs/{id}/stream     -> SSE live stage events
  POST /runs/{id}/decision   -> human approve/reject-with-reason
  POST /seed-demo            -> run all corpus invoices to populate the dashboard
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json

from . import orchestrator, store
from .contracts import Decision, Notification, RunRecord
from dotenv import load_dotenv

load_dotenv(orchestrator.REPO / "backend" / ".env")  # local convenience; hosts inject env directly
_DIST = orchestrator.REPO / "frontend" / "dist"

app = FastAPI(title="PayFlow", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

# run_id -> invoice_file, so the SSE stream knows what to process
_pending: dict[str, str] = {}


@app.on_event("startup")
def _startup() -> None:
    store.init_db()
    if not store.list_vendors():
        store.load_masters()
    if os.getenv("SEED_DEMO_ON_START") == "1" and not store.list_runs():
        for pdf in sorted(orchestrator.INVOICES.glob("*.pdf")):
            try:
                orchestrator.process(_new_run_id(), pdf.name)  # populate dashboard once
            except Exception:
                pass


def _new_run_id() -> str:
    return "run_" + uuid.uuid4().hex[:12]


# ── models ──
class CreateRunBody(BaseModel):
    invoice_file: Optional[str] = None
    wait: bool = False


class DecisionBody(BaseModel):
    decision: str
    note: Optional[str] = None


# ── routes ──
@app.get("/health")
def health() -> dict:
    import os
    return {"status": "ok", "provider": os.getenv("EXTRACTION_PROVIDER", "gemini"),
            "runs": len(store.list_runs()), "vendors": len(store.list_vendors())}


@app.get("/runs", response_model=list[RunRecord])
def list_runs() -> list[RunRecord]:
    return store.list_runs()


@app.get("/runs/{run_id}", response_model=RunRecord)
def get_run(run_id: str) -> RunRecord:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, f"run {run_id} not found")
    return run


@app.post("/runs")
def create_run(body: CreateRunBody, wait: bool = False):
    invoice_file = body.invoice_file or orchestrator.default_invoice()
    if not invoice_file:
        raise HTTPException(400, "no invoice_file provided and no corpus available")
    try:
        orchestrator.resolve_pdf(invoice_file)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    run_id = _new_run_id()
    if wait or body.wait:  # synchronous — used by curl/tests
        return orchestrator.process(run_id, invoice_file)
    _pending[run_id] = invoice_file
    return {"run_id": run_id, "invoice_file": invoice_file}


@app.post("/runs/upload")
async def upload_run(file: UploadFile = File(...), wait: bool = False):
    safe = Path(file.filename or "").name  # strip path components — traversal guard
    if not safe:
        raise HTTPException(400, "missing or invalid filename")
    orchestrator.UPLOADS.mkdir(parents=True, exist_ok=True)
    dest = orchestrator.UPLOADS / safe
    dest.write_bytes(await file.read())
    run_id = _new_run_id()
    if wait:
        return orchestrator.process(run_id, safe)
    _pending[run_id] = safe
    return {"run_id": run_id, "invoice_file": safe}


@app.get("/runs/{run_id}/stream")
async def stream_run(run_id: str):
    invoice_file = _pending.get(run_id)
    if not invoice_file:
        existing = store.get_run(run_id)  # already processed → replay is a no-op elsewhere
        if existing:
            invoice_file = existing.invoice_file
    if not invoice_file:
        raise HTTPException(404, f"no pending run {run_id}")

    async def gen():
        try:
            async for ev in orchestrator.stream(run_id, invoice_file):
                yield {"data": ev.model_dump_json()}
        finally:
            _pending.pop(run_id, None)

    return EventSourceResponse(gen())


@app.post("/runs/{run_id}/decision", response_model=RunRecord)
def human_decision(run_id: str, body: DecisionBody) -> RunRecord:
    run = store.get_run(run_id)
    if not run or not run.result:
        raise HTTPException(404, f"run {run_id} not found")
    try:
        run.result.decision = Decision(body.decision.upper())
    except ValueError:
        raise HTTPException(400, f"invalid decision '{body.decision}'")
    run.actor = "human"
    note = Notification(type="human_decision", recipient="audit",
                        message=f"Human set {run.result.decision.value}"
                                + (f": {body.note}" if body.note else ""))
    run.result.notifications.append(note)
    store.save_run(run)
    store.save_notification(note, run_id=run_id)
    return run


@app.post("/seed-demo")
def seed_demo() -> dict:
    pdfs = sorted(orchestrator.INVOICES.glob("*.pdf"))
    counts: dict[str, int] = {"APPROVE": 0, "HOLD": 0, "REJECT": 0}
    runs = []
    for pdf in pdfs:
        run = orchestrator.process(_new_run_id(), pdf.name)
        d = run.result.decision.value if run.result else "?"
        counts[d] = counts.get(d, 0) + 1
        runs.append({"file": pdf.name, "decision": d})
    return {"processed": len(pdfs), "counts": counts, "runs": runs}

@app.get("/invoices")
def list_invoices() -> list[dict]:
    """The real corpus invoices, with scenario labels from the manifest (for the Live Run picker)."""
    manifest = orchestrator.REPO / "data" / "fixtures" / "manifest.json"
    labels: dict[str, dict] = {}
    if manifest.exists():
        raw = json.loads(manifest.read_text())
        entries = raw if isinstance(raw, list) else raw.get("invoices") or list(raw.values())
        for e in entries:
            if isinstance(e, dict):
                fn = e.get("filename") or e.get("file")
                if fn:
                    labels[Path(fn).name] = {"scenario": e.get("scenario"),
                                             "expected_decision": e.get("expected_decision")}
    out = []
    for pdf in sorted(orchestrator.INVOICES.glob("*.pdf")):
        meta = labels.get(pdf.name, {})
        out.append({"filename": pdf.name, "scenario": meta.get("scenario"),
                    "expected_decision": meta.get("expected_decision")})
    return out


@app.get("/invoices/{name}")
def get_invoice(name: str):
    p = orchestrator.INVOICES / Path(name).name
    if not p.exists():
        raise HTTPException(404, f"invoice {name} not found")
    return FileResponse(str(p), media_type="application/pdf")


# ── serve the built frontend (single-origin production) ──
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        target = _DIST / full_path
        if full_path and target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(_DIST / "index.html"))

