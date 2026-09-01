import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useRuns } from "@/lib/useRuns";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardBody } from "@/components/ui/Card";
import { StatusPill } from "@/components/StatusPill";
import { useActions, latestResolution } from "@/lib/notes";
import { dateTime, duration, money } from "@/lib/format";
import { STAGES } from "@/contracts";
import { cn } from "@/lib/cn";
import { Bot, User, ShieldCheck, ArrowRight, Check, X, Minus } from "lucide-react";

export function AuditTrail() {
  const { runs } = useRuns();
  const actions = useActions();

  const sorted = useMemo(
    () =>
      [...runs]
        .filter((r) => r.result)
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [runs],
  );

  return (
    <div>
      <PageHeader
        title="Audit Trail"
        subtitle="Immutable, tamper-evident log of every run and stage."
        actions={
          <span className="flex items-center gap-1.5 text-xs text-slate-400">
            <ShieldCheck className="h-4 w-4" /> {sorted.length} runs recorded
          </span>
        }
      />

      <div className="space-y-3 p-8">
        {sorted.map((r) => {
          const res = latestResolution(r.run_id);
          void actions;
          return (
            <Link key={r.run_id} to={`/runs/${r.run_id}`}>
              <Card className="transition-shadow hover:shadow-lift">
                <CardBody className="flex flex-wrap items-center gap-x-6 gap-y-3 py-3.5">
                  <div className="min-w-[8rem]">
                    <div className="tnum font-mono text-sm font-semibold text-slate-800 dark:text-slate-100">
                      {r.run_id}
                    </div>
                    <div className="text-[11px] text-slate-400">{dateTime(r.created_at)}</div>
                  </div>

                  <div className="min-w-[10rem] flex-1">
                    <div className="text-sm text-slate-700 dark:text-slate-200">
                      {r.extract?.vendor_name}
                    </div>
                    <div className="tnum font-mono text-[11px] text-slate-400">
                      {r.extract?.invoice_number} · {money(r.extract?.total, r.extract?.currency)}
                    </div>
                  </div>

                  {/* mini stage strip */}
                  <div className="flex items-center gap-1">
                    {STAGES.map((s) => {
                      const st = r.stages.find((x) => x.stage === s);
                      const status = st?.status ?? "pending";
                      return (
                        <span
                          key={s}
                          title={`${s}: ${status}`}
                          className={cn(
                            "flex h-4 w-4 items-center justify-center rounded-full text-white",
                            status === "ok"
                              ? "bg-accent"
                              : status === "fail"
                                ? "bg-rose-500"
                                : "bg-slate-200 dark:bg-slate-700",
                          )}
                        >
                          {status === "ok" ? (
                            <Check className="h-2.5 w-2.5" strokeWidth={3.5} />
                          ) : status === "fail" ? (
                            <X className="h-2.5 w-2.5" strokeWidth={3.5} />
                          ) : (
                            <Minus className="h-2.5 w-2.5 text-slate-400" />
                          )}
                        </span>
                      );
                    })}
                  </div>

                  <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
                    {r.actor === "human" ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
                    {r.actor}
                  </div>

                  <div className="tnum w-16 text-right font-mono text-xs text-slate-500">
                    {duration(r.cycle_time_ms)}
                  </div>

                  <div className="flex items-center gap-2">
                    {res && (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                        {res.action === "APPROVE" ? "human-approved" : "human-rejected"}
                      </span>
                    )}
                    <StatusPill decision={r.result!.decision} size="sm" />
                    <ArrowRight className="h-4 w-4 text-slate-300" />
                  </div>
                </CardBody>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
