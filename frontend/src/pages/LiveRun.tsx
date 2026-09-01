import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { STAGES } from "@/contracts";
import type { Stage, InvoiceExtract, DecisionResult, SSEEvent } from "@/contracts";
import { createRun, uploadRun, streamRun, getRun, listInvoices, invoiceUrl } from "@/api";
import type { InvoiceMeta } from "@/api";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Stepper, type StageState } from "@/components/Stepper";
import { DocumentPreview } from "@/components/DocumentPreview";
import { ExtractedFields } from "@/components/ExtractedFields";
import { VerdictCard } from "@/components/VerdictCard";
import { UploadCloud, Play, RotateCcw, FileText, ArrowRight } from "lucide-react";
import { duration } from "@/lib/format";

type Phase = "idle" | "running" | "done";

const initialStates = (): Record<Stage, StageState> =>
  Object.fromEntries(STAGES.map((s) => [s, "pending"])) as Record<Stage, StageState>;

export function LiveRun() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [states, setStates] = useState<Record<Stage, StageState>>(initialStates);
  const [durations, setDurations] = useState<Partial<Record<Stage, number>>>({});
  const [extract, setExtract] = useState<InvoiceExtract | undefined>();
  const [result, setResult] = useState<DecisionResult | undefined>();
  const [fileName, setFileName] = useState<string>("01_clean_exact.pdf");
  const [runId, setRunId] = useState<string>();
  const [cycle, setCycle] = useState<number>();
  const handleRef = useRef<{ close: () => void }>();
  const startRef = useRef<number>(0);

  const [invoices, setInvoices] = useState<InvoiceMeta[]>([]);
  useEffect(() => { listInvoices().then((xs) => { if (xs.length) setInvoices(xs); }); }, []);

  const [uploadedFile, setUploadedFile] = useState<File | undefined>();
  const [uploadedUrl, setUploadedUrl] = useState<string | undefined>();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pickFile = (f: File) => {
    setUploadedFile(f);
    setUploadedUrl((u) => { if (u) URL.revokeObjectURL(u); return URL.createObjectURL(f); });
    setFileName(f.name);
  };

  const reset = useCallback(() => {
    handleRef.current?.close();
    setPhase("idle");
    setStates(initialStates());
    setDurations({});
    setExtract(undefined);
    setResult(undefined);
    setCycle(undefined);
  }, []);

  const start = useCallback(async () => {
    reset();
    setPhase("running");
    startRef.current = performance.now();
    const id = uploadedFile ? await uploadRun(uploadedFile) : await createRun(fileName);
    setRunId(id);

    handleRef.current = streamRun(
      id,
      (ev: SSEEvent) => {
        if (!ev.stage) {
          if (ev.type === "run_completed") {
            setPhase("done");
            setCycle(Math.round(performance.now() - startRef.current));
          }
          return;
        }
        const stage = ev.stage;
        if (ev.type === "stage_started") {
          setStates((s) => ({ ...s, [stage]: "running" }));
        } else if (ev.type === "stage_completed") {
          const st: StageState = ev.status === "fail" ? "failed" : ev.status === "skipped" ? "skipped" : "done";
          setStates((s) => ({ ...s, [stage]: st }));
          if (typeof ev.payload?.__duration === "number") {
            setDurations((d) => ({ ...d, [stage]: ev.payload.__duration as number }));
          }
          // real extracted fields arrive on completion (onDone)
        }
      },
      async (rec) => {
        const full = (await getRun(rec.run_id)) ?? rec;
        setExtract(full.extract);
        setResult(full.result);
        setStates((s) => {
          const next = { ...s };
          full.stages.forEach((st) => {
            next[st.stage] = st.status === "fail" ? "failed" : st.status === "skipped" ? "skipped" : "done";
          });
          return next;
        });
        setDurations(Object.fromEntries(full.stages.map((st) => [st.stage, st.duration_ms])));
        setCycle(full.cycle_time_ms);
        setPhase("done");
      },
    );
  }, [fileName, uploadedFile, reset]);

  useEffect(() => () => handleRef.current?.close(), []);
  useEffect(() => () => { if (uploadedUrl) URL.revokeObjectURL(uploadedUrl); }, [uploadedUrl]);

  return (
    <div>
      <PageHeader
        title="Live Run"
        subtitle="Drop a vendor invoice — watch it move from paper to a defensible decision."
        actions={
          phase === "done" ? (
            <>
              {runId && (
                <Link to={`/runs/${runId}`}>
                  <Button variant="secondary">
                    Open audit trail <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
              )}
              <Button variant="primary" onClick={start}>
                <RotateCcw className="h-4 w-4" /> Run again
              </Button>
            </>
          ) : phase === "idle" ? (
            <Button variant="primary" onClick={start}>
              <Play className="h-4 w-4" /> Process invoice
            </Button>
          ) : (
            <Button variant="secondary" disabled>
              Processing…
            </Button>
          )
        }
      />

      <div className="space-y-6 p-8">
        {/* invoice picker — real corpus */}
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">Sample invoice</label>
          <select
            value={fileName}
            onChange={(e) => { setUploadedFile(undefined); setUploadedUrl((u) => { if (u) URL.revokeObjectURL(u); return undefined; }); setFileName(e.target.value); reset(); }}
            disabled={phase === "running"}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-mono text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
          >
            {(invoices.length ? invoices.map((i) => i.filename) : [fileName]).map((fn) => {
              const meta = invoices.find((i) => i.filename === fn);
              return <option key={fn} value={fn}>{fn}{meta?.scenario ? ` — ${meta.scenario}` : ""}</option>;
            })}
          </select>
          {invoices.find((i) => i.filename === fileName)?.expected_decision && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              expected: {invoices.find((i) => i.filename === fileName)?.expected_decision}
            </span>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) pickFile(f); }}
        />
        {/* drop zone (idle only) */}
        {phase === "idle" && (
          <button
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const f = e.dataTransfer.files?.[0];
              if (f) pickFile(f);
            }}
            className="group flex w-full flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-slate-300 bg-white/50 py-14 transition-colors hover:border-accent hover:bg-accent-soft/40 dark:border-slate-700 dark:bg-slate-900/40 dark:hover:border-accent"
          >
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-accent-soft text-accent transition-transform group-hover:scale-105 dark:bg-accent-softdark/50 dark:text-indigo-300">
              <UploadCloud className="h-7 w-7" />
            </span>
            <div className="text-center">
              <div className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                Drop a PDF invoice — or click to choose a file
              </div>
              <div className="mt-1 flex items-center justify-center gap-1.5 text-xs text-slate-400">
                <FileText className="h-3.5 w-3.5" />
                <span className="font-mono">{fileName}</span>
              </div>
            </div>
          </button>
        )}

        {/* stepper */}
        <Card>
          <CardBody className="px-8 py-6">
            <Stepper states={states} durations={durations} />
            {cycle != null && (
              <div className="mt-4 text-center text-xs text-slate-400">
                Cycle time <span className="tnum font-mono text-slate-600 dark:text-slate-300">{duration(cycle)}</span>
              </div>
            )}
          </CardBody>
        </Card>

        {/* side by side */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card className="flex flex-col">
            <CardHeader title="Source document" subtitle="Left: what arrived" />
            <CardBody className="flex-1">
              <DocumentPreview fileUrl={uploadedUrl ?? invoiceUrl(fileName)} fileName={fileName} />
            </CardBody>
          </Card>

          <Card className="flex flex-col">
            <CardHeader
              title="Extracted fields"
              subtitle="Right: what the model read — with per-field confidence"
            />
            <CardBody className="flex-1">
              {extract ? (
                <ExtractedFields extract={extract} />
              ) : (
                <div className="flex h-full min-h-[300px] flex-col items-center justify-center gap-2 text-sm text-slate-400">
                  {phase === "running" ? (
                    <>
                      <span className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                      Reading document…
                    </>
                  ) : (
                    "Fields appear once extraction completes."
                  )}
                </div>
              )}
            </CardBody>
          </Card>
        </div>

        {/* verdict */}
        {result && (
          <div className="animate-fadein">
            <VerdictCard result={result} />
          </div>
        )}
      </div>
    </div>
  );
}
