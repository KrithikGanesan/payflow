import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { RunRecord } from "@/contracts";
import { getRun } from "@/api";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { VerdictCard } from "@/components/VerdictCard";
import { Timeline } from "@/components/Timeline";
import { DocumentPreview } from "@/components/DocumentPreview";
import { ExtractedFields } from "@/components/ExtractedFields";
import { StatusPill } from "@/components/StatusPill";
import { ReasonDialog } from "@/components/ReasonDialog";
import { addAction, useActions, actionsFor } from "@/lib/notes";
import { dateTime, duration } from "@/lib/format";
import { ArrowLeft, Check, Ban, Bot, User, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/cn";

export function RunDetail() {
  const { id } = useParams();
  const [run, setRun] = useState<RunRecord>();
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState<"APPROVE" | "REJECT" | null>(null);
  useActions(); // re-render on new actions

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getRun(id!).then((r) => {
      if (alive) {
        setRun(r);
        setLoading(false);
      }
    });
    return () => {
      alive = false;
    };
  }, [id]);

  if (loading)
    return (
      <div className="flex h-64 items-center justify-center text-slate-400">Loading run…</div>
    );
  if (!run)
    return (
      <div className="p-8">
        <p className="text-slate-500">Run not found.</p>
        <Link to="/history" className="text-accent">← Back to history</Link>
      </div>
    );

  const actions = actionsFor(run.run_id);

  const submit = (reason: string) => {
    addAction({ run_id: run.run_id, action: dialog!, actor: "a.ryan (clerk)", reason });
    setDialog(null);
  };

  return (
    <div>
      <PageHeader
        title={`Run ${run.run_id}`}
        subtitle={run.invoice_file}
        actions={
          <div className="flex items-center gap-2">
            {run.result && <StatusPill decision={run.result.decision} />}
            {run.result?.decision !== "APPROVE" && (
              <Button variant="success" size="sm" onClick={() => setDialog("APPROVE")}>
                <Check className="h-4 w-4" /> Approve with reason
              </Button>
            )}
            {run.result?.decision !== "REJECT" && (
              <Button variant="danger" size="sm" onClick={() => setDialog("REJECT")}>
                <Ban className="h-4 w-4" /> Reject
              </Button>
            )}
          </div>
        }
      />

      <div className="p-8">
        <Link
          to="/history"
          className="mb-4 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> History
        </Link>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* left: verdict + audit */}
          <div className="space-y-6 lg:col-span-2">
            {run.result && <VerdictCard result={run.result} />}

            {actions.length > 0 && (
              <Card>
                <CardHeader title="Human actions" subtitle="Overrides & notes on the record" />
                <CardBody className="space-y-3">
                  {actions.map((a, i) => (
                    <div key={i} className="flex gap-3">
                      <span
                        className={cn(
                          "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
                          a.action === "APPROVE"
                            ? "bg-emerald-100 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400"
                            : a.action === "REJECT"
                              ? "bg-rose-100 text-rose-600 dark:bg-rose-950/50 dark:text-rose-400"
                              : "bg-slate-100 text-slate-500 dark:bg-slate-800",
                        )}
                      >
                        {a.action === "APPROVE" ? <Check className="h-3.5 w-3.5" /> : a.action === "REJECT" ? <Ban className="h-3.5 w-3.5" /> : <User className="h-3.5 w-3.5" />}
                      </span>
                      <div>
                        <div className="text-sm text-slate-700 dark:text-slate-200">
                          <span className="font-semibold">{a.actor}</span> {a.action.toLowerCase()}d this run
                        </div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">"{a.reason}"</div>
                        <div className="mt-0.5 text-[11px] text-slate-400">{dateTime(a.ts)}</div>
                      </div>
                    </div>
                  ))}
                </CardBody>
              </Card>
            )}

            <Card>
              <CardHeader
                title="Audit trail"
                subtitle="Immutable stage log — rule fired, values, actor, timestamp"
                right={
                  <span className="flex items-center gap-1 text-[11px] text-slate-400">
                    <ShieldCheck className="h-3.5 w-3.5" /> tamper-evident
                  </span>
                }
              />
              <CardBody>
                <Timeline run={run} />
              </CardBody>
            </Card>
          </div>

          {/* right: doc + fields */}
          <div className="space-y-6">
            <Card>
              <CardHeader
                title="Extracted fields"
                right={
                  <span className="flex items-center gap-1 text-[11px] text-slate-400">
                    <Bot className="h-3.5 w-3.5" /> {run.actor}
                  </span>
                }
              />
              <CardBody>
                <ExtractedFields extract={run.extract} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Source document" />
              <CardBody>
                <DocumentPreview extract={run.extract} fileName={run.invoice_file} />
              </CardBody>
            </Card>
            <div className="text-center text-xs text-slate-400">
              Processed {dateTime(run.created_at)} · cycle {duration(run.cycle_time_ms)}
            </div>
          </div>
        </div>
      </div>

      <ReasonDialog
        open={dialog !== null}
        action={dialog ?? "APPROVE"}
        runLabel={run.run_id}
        onClose={() => setDialog(null)}
        onSubmit={submit}
      />
    </div>
  );
}
