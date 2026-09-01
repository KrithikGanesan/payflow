import { useEffect, useMemo, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import type { RunRecord } from "@/contracts";
import { useRuns } from "@/lib/useRuns";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardBody } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ReasonList } from "@/components/ReasonList";
import { StatusPill } from "@/components/StatusPill";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { ReasonDialog } from "@/components/ReasonDialog";
import { addAction, useActions, latestResolution } from "@/lib/notes";
import { money, relativeTime } from "@/lib/format";
import { cn } from "@/lib/cn";
import { Check, Ban, Inbox, ArrowRight, CheckCircle2 } from "lucide-react";

export function ExceptionQueue() {
  const { runs } = useRuns();
  const actions = useActions();
  const [selected, setSelected] = useState(0);
  const [dialog, setDialog] = useState<"APPROVE" | "REJECT" | null>(null);

  const queue = useMemo(
    () =>
      runs.filter(
        (r) => r.result?.decision === "HOLD" && !latestResolution(r.run_id),
      ),
    [runs, actions],
  );

  const resolved = useMemo(
    () => runs.filter((r) => r.result?.decision === "HOLD" && latestResolution(r.run_id)),
    [runs, actions],
  );

  useEffect(() => {
    if (selected >= queue.length) setSelected(Math.max(0, queue.length - 1));
  }, [queue.length, selected]);

  const active: RunRecord | undefined = queue[selected];

  const resolve = useCallback(
    (reason: string) => {
      if (!active) return;
      addAction({ run_id: active.run_id, action: dialog!, actor: "a.ryan (clerk)", reason });
      setDialog(null);
    },
    [active, dialog],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (dialog) return;
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setSelected((s) => Math.min(queue.length - 1, s + 1));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setSelected((s) => Math.max(0, s - 1));
      } else if (e.key === "a" && active) {
        setDialog("APPROVE");
      } else if (e.key === "r" && active) {
        setDialog("REJECT");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [queue.length, active, dialog]);

  return (
    <div>
      <PageHeader
        title="Exception Queue"
        subtitle="Pre-investigated holds with evidence — clear them fast."
        actions={
          <div className="hidden items-center gap-2 text-[11px] text-slate-400 md:flex">
            <span className="kbd">j</span>
            <span className="kbd">k</span> navigate
            <span className="kbd">a</span> approve
            <span className="kbd">r</span> reject
          </div>
        }
      />

      <div className="p-8">
        {queue.length === 0 ? (
          <Card>
            <CardBody className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <span className="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50 text-emerald-500 dark:bg-emerald-950/40">
                <CheckCircle2 className="h-7 w-7" />
              </span>
              <div>
                <div className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                  Queue clear
                </div>
                <div className="text-xs text-slate-400">
                  {resolved.length > 0
                    ? `${resolved.length} exception${resolved.length > 1 ? "s" : ""} resolved this session.`
                    : "No holds awaiting review."}
                </div>
              </div>
            </CardBody>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,340px)_1fr]">
            {/* list */}
            <div className="space-y-2">
              <div className="flex items-center justify-between px-1 text-xs text-slate-400">
                <span className="flex items-center gap-1.5">
                  <Inbox className="h-3.5 w-3.5" /> {queue.length} awaiting review
                </span>
              </div>
              {queue.map((r, i) => {
                const driver = r.result!.reasons.find((x) => x.severity !== "INFO");
                return (
                  <button
                    key={r.run_id}
                    onClick={() => setSelected(i)}
                    className={cn(
                      "w-full rounded-xl border p-3 text-left transition-colors",
                      i === selected
                        ? "border-accent bg-accent-soft/60 ring-1 ring-accent/40 dark:bg-accent-softdark/30"
                        : "border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900/50 dark:hover:border-slate-700",
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                        {r.extract?.vendor_name}
                      </span>
                      <span className="tnum font-mono text-sm font-medium text-slate-700 dark:text-slate-200">
                        {money(r.extract?.total, r.extract?.currency)}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <span className="tnum font-mono text-[11px] text-slate-400">
                        {r.extract?.invoice_number}
                      </span>
                      <ConfidenceBadge value={r.result!.overall_confidence} />
                      <span className="ml-auto text-[11px] text-slate-400">
                        {relativeTime(r.created_at)}
                      </span>
                    </div>
                    {driver && (
                      <div className="mt-2 truncate rounded bg-amber-50 px-2 py-1 text-[11px] text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                        {driver.rule}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>

            {/* detail */}
            {active && (
              <Card className="flex flex-col">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-bold text-slate-900 dark:text-white">
                        {active.extract?.vendor_name}
                      </h3>
                      <StatusPill decision="HOLD" size="sm" />
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-400">
                      <span className="tnum font-mono">{active.extract?.invoice_number}</span>
                      <span>·</span>
                      <span className="tnum font-mono font-medium text-slate-600 dark:text-slate-300">
                        {money(active.extract?.total, active.extract?.currency)}
                      </span>
                      <span>·</span>
                      <span>{active.result!.routed_to}</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="success" size="sm" onClick={() => setDialog("APPROVE")}>
                      <Check className="h-4 w-4" /> Approve
                    </Button>
                    <Button variant="danger" size="sm" onClick={() => setDialog("REJECT")}>
                      <Ban className="h-4 w-4" /> Reject
                    </Button>
                  </div>
                </div>
                <CardBody className="flex-1 space-y-4">
                  <div>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Evidence
                    </div>
                    <ReasonList reasons={active.result!.reasons} />
                  </div>
                  <Link
                    to={`/runs/${active.run_id}`}
                    className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
                  >
                    Open full audit trail <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </CardBody>
              </Card>
            )}
          </div>
        )}
      </div>

      <ReasonDialog
        open={dialog !== null}
        action={dialog ?? "APPROVE"}
        runLabel={active?.run_id ?? ""}
        onClose={() => setDialog(null)}
        onSubmit={resolve}
      />
    </div>
  );
}
