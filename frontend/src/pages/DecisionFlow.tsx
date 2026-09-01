import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { STAGES } from "@/contracts";
import type { Stage, DecisionResult, SSEEvent } from "@/contracts";
import { createRun, uploadRun, streamRun, getRun, listInvoices } from "@/api";
import type { InvoiceMeta } from "@/api";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardBody } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Stepper, type StageState } from "@/components/Stepper";
import { VerdictCard } from "@/components/VerdictCard";
import { deriveNodes, type FlowNodeVM, type FlowState } from "@/lib/flowModel";
import { Play, RotateCcw, UploadCloud, ArrowRight } from "lucide-react";

type Phase = "idle" | "running" | "done";
const initialStates = (): Record<Stage, StageState> =>
  Object.fromEntries(STAGES.map((s) => [s, "pending"])) as Record<Stage, StageState>;

const TONE: Record<FlowState, { dot: string; text: string; panel: string; label: string }> = {
  pass:    { dot: "bg-emerald-500", text: "text-emerald-700 dark:text-emerald-400", panel: "border-emerald-200 bg-emerald-50/60 dark:border-emerald-900 dark:bg-emerald-950/20", label: "PASS" },
  hold:    { dot: "bg-amber-500",   text: "text-amber-700 dark:text-amber-400",     panel: "border-amber-300 bg-amber-50/70 dark:border-amber-900 dark:bg-amber-950/20", label: "HOLD" },
  reject:  { dot: "bg-rose-600",    text: "text-rose-700 dark:text-rose-400",       panel: "border-rose-300 bg-rose-50/70 dark:border-rose-900 dark:bg-rose-950/20", label: "REJECT" },
  skipped: { dot: "bg-slate-300 dark:bg-slate-700", text: "text-slate-400",         panel: "border-slate-200 bg-slate-50/50 dark:border-slate-800 dark:bg-slate-900/30", label: "SKIPPED" },
  active:  { dot: "bg-accent",      text: "text-accent",                            panel: "border-accent/40 bg-accent-soft/50 dark:bg-accent-softdark/20", label: "CHECKING…" },
  pending: { dot: "bg-slate-200 dark:bg-slate-800", text: "text-slate-300 dark:text-slate-600", panel: "border-slate-200/70 dark:border-slate-800/70", label: "" },
};

export function DecisionFlow() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [states, setStates] = useState<Record<Stage, StageState>>(initialStates);
  const [fileName, setFileName] = useState<string>("05_tax_over_tolerance.pdf");
  const [invoices, setInvoices] = useState<InvoiceMeta[]>([]);
  const [result, setResult] = useState<DecisionResult | undefined>();
  const [nodes, setNodes] = useState<FlowNodeVM[]>([]);
  const [revealIdx, setRevealIdx] = useState(0);
  const [runId, setRunId] = useState<string>();
  const [uploadedFile, setUploadedFile] = useState<File | undefined>();
  const [speed, setSpeed] = useState(1);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const handleRef = useRef<{ close: () => void }>();

  useEffect(() => { listInvoices().then((xs) => { if (xs.length) setInvoices(xs); }); }, []);
  useEffect(() => () => handleRef.current?.close(), []);

  const pickFile = (f: File) => { setUploadedFile(f); setFileName(f.name); };

  // reveal the gate ledger node-by-node once the result lands
  useEffect(() => {
    if (phase !== "done" || !nodes.length || revealIdx > nodes.length) return;
    const t = setTimeout(() => setRevealIdx((i) => i + 1), 460 / speed);
    return () => clearTimeout(t);
  }, [phase, nodes, revealIdx, speed]);

  const reset = useCallback(() => {
    handleRef.current?.close();
    setPhase("idle"); setStates(initialStates()); setResult(undefined); setNodes([]); setRevealIdx(0);
  }, []);

  const run = useCallback(async () => {
    reset(); setPhase("running");
    const id = uploadedFile ? await uploadRun(uploadedFile) : await createRun(fileName);
    setRunId(id);
    handleRef.current = streamRun(
      id,
      (ev: SSEEvent) => {
        if (!ev.stage) return;
        const st: StageState = ev.type === "stage_started" ? "running" : ev.status === "fail" ? "failed" : ev.status === "skipped" ? "skipped" : "done";
        setStates((s) => ({ ...s, [ev.stage as Stage]: st }));
      },
      async (rec) => {
        const full = (await getRun(rec.run_id)) ?? rec;
        setStates((s) => { const n = { ...s }; full.stages.forEach((x) => { n[x.stage] = x.status === "fail" ? "failed" : "done"; }); return n; });
        if (full.result) { setResult(full.result); setNodes(deriveNodes(full.result)); }
        setRevealIdx(0); setPhase("done");
      },
    );
  }, [fileName, uploadedFile, reset]);

  const displayState = (n: FlowNodeVM, i: number): FlowState =>
    i < revealIdx ? n.state : i === revealIdx ? "active" : "pending";

  return (
    <div>
      <PageHeader
        title="Decision Flow"
        subtitle="Run an invoice and watch exactly what happened — every gate, in order, with the numbers it compared."
        actions={
          phase === "done" ? (
            <>
              {runId && <Link to={`/runs/${runId}`}><Button variant="secondary">Audit trail <ArrowRight className="h-4 w-4" /></Button></Link>}
              <Button variant="secondary" onClick={() => setRevealIdx(0)}><RotateCcw className="h-4 w-4" /> Replay</Button>
              <Button variant="primary" onClick={run}><Play className="h-4 w-4" /> Run again</Button>
            </>
          ) : (
            <Button variant="primary" onClick={run} disabled={phase === "running"}>
              <Play className="h-4 w-4" /> {phase === "running" ? "Running…" : "Run trace"}
            </Button>
          )
        }
      />
      <div className="space-y-6 p-8">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">Invoice</label>
          <select value={uploadedFile ? "__uploaded__" : fileName}
            onChange={(e) => { setUploadedFile(undefined); setFileName(e.target.value); reset(); }}
            disabled={phase === "running"}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-mono text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200">
            {uploadedFile && <option value="__uploaded__">{uploadedFile.name} (uploaded)</option>}
            {(invoices.length ? invoices.map((i) => i.filename) : [fileName]).map((fn) => {
              const m = invoices.find((i) => i.filename === fn);
              return <option key={fn} value={fn}>{fn}{m?.scenario ? ` — ${m.scenario}` : ""}</option>;
            })}
          </select>
          <input ref={fileInputRef} type="file" accept="application/pdf" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) pickFile(f); }} />
          <Button variant="secondary" size="sm" onClick={() => fileInputRef.current?.click()} disabled={phase === "running"}>
            <UploadCloud className="h-4 w-4" /> Upload
          </Button>
          <span className="ml-auto flex items-center gap-1 text-xs text-slate-400">
            speed
            {[0.5, 1, 2].map((s) => (
              <button key={s} onClick={() => setSpeed(s)} className={"rounded px-1.5 py-0.5 " + (speed === s ? "bg-accent text-white" : "hover:bg-slate-100 dark:hover:bg-slate-800")}>{s}×</button>
            ))}
          </span>
        </div>

        <Card><CardBody className="px-8 py-6"><Stepper states={states} /></CardBody></Card>

        {phase === "done" && (
          <Card>
            <CardBody className="p-6">
              <div className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-400">What happened — gate by gate</div>
              <ol>
                {nodes.map((n, i) => {
                  const st = displayState(n, i);
                  const tone = TONE[st];
                  const last = i === nodes.length - 1;
                  const resolved = st !== "pending" && st !== "active";
                  return (
                    <li key={n.id} className={"flex gap-3 " + (st === "pending" ? "opacity-40" : "animate-fadein")}>
                      <div className="flex flex-col items-center">
                        <span className={"mt-1 h-3 w-3 shrink-0 rounded-full " + tone.dot + (st === "active" ? " animate-pulsering" : "")} />
                        {!last && <span className="my-1 w-px flex-1 bg-slate-200 dark:bg-slate-800" />}
                      </div>
                      <div className={"mb-2 flex-1 rounded-lg border px-4 py-3 " + tone.panel}>
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                            {n.label}
                            {n.driving && resolved && <span className="ml-2 rounded bg-slate-900/5 px-1.5 py-0.5 text-[10px] font-bold uppercase text-slate-500 dark:bg-white/10">drove decision</span>}
                          </span>
                          <span className={"text-[11px] font-bold uppercase tracking-wide " + tone.text}>{tone.label}</span>
                        </div>
                        {resolved && (
                          <>
                            {n.chips.length > 0 && (
                              <div className="mt-1.5 flex flex-wrap gap-1.5">
                                {n.chips.map((c, k) => (
                                  <span key={k} className="tnum rounded bg-white px-1.5 py-0.5 font-mono text-[11px] text-slate-600 shadow-sm dark:bg-slate-800 dark:text-slate-300">{c.k}: {c.v}</span>
                                ))}
                              </div>
                            )}
                            {n.reasons.map((r, k) => (<p key={k} className="mt-1.5 text-xs leading-snug text-slate-600 dark:text-slate-300">{r.message}</p>))}
                            {st === "pass" && n.reasons.length === 0 && <p className="mt-1 text-xs text-slate-400">Passed — no issues.</p>}
                          </>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            </CardBody>
          </Card>
        )}

        {phase === "done" && result && revealIdx > nodes.length && (
          <div className="animate-fadein"><VerdictCard result={result} /></div>
        )}
      </div>
    </div>
  );
}
