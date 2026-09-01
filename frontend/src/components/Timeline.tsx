import type { RunRecord, StageResult } from "@/contracts";
import { cn } from "@/lib/cn";
import { duration, dateTime } from "@/lib/format";
import { Check, X, Minus, Bot, User } from "lucide-react";

const STAGE_TITLE: Record<string, string> = {
  RECEIVED: "Received",
  EXTRACTED: "Extracted",
  CODED: "Coded",
  MATCHED: "Matched",
  VALIDATED: "Validated",
  DECIDED: "Decided",
};

function StatusDot({ status }: { status: string }) {
  if (status === "ok")
    return (
      <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-accent bg-accent text-white">
        <Check className="h-3.5 w-3.5" strokeWidth={3} />
      </span>
    );
  if (status === "fail")
    return (
      <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-rose-500 bg-rose-500 text-white">
        <X className="h-3.5 w-3.5" strokeWidth={3} />
      </span>
    );
  return (
    <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-slate-200 bg-slate-100 text-slate-400 dark:border-slate-700 dark:bg-slate-800">
      <Minus className="h-3.5 w-3.5" />
    </span>
  );
}

function KV({ output }: { output: Record<string, unknown> }) {
  const entries = Object.entries(output).filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (entries.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
      {entries.map(([k, v]) => (
        <div key={k} className="text-[11px]">
          <span className="text-slate-400 dark:text-slate-500">{k}: </span>
          <span className="tnum font-mono text-slate-600 dark:text-slate-300">
            {typeof v === "number" ? formatNum(v) : String(v)}
          </span>
        </div>
      ))}
    </div>
  );
}

function formatNum(v: number): string {
  if (v > 0 && v < 1) return v.toFixed(2);
  return new Intl.NumberFormat("en-US").format(v);
}

export function Timeline({ run }: { run: RunRecord }) {
  const baseTime = new Date(run.created_at).getTime();
  let acc = 0;
  return (
    <ol className="relative space-y-0">
      {run.stages.map((st: StageResult, i) => {
        const at = new Date(baseTime + acc).toISOString();
        acc += st.duration_ms;
        const last = i === run.stages.length - 1;
        return (
          <li key={st.stage} className="relative flex gap-4 pb-6">
            {!last && (
              <span
                className={cn(
                  "absolute left-[11px] top-6 h-full w-0.5",
                  st.status === "ok" || st.status === "fail"
                    ? "bg-accent/40"
                    : "bg-slate-200 dark:bg-slate-700",
                )}
              />
            )}
            <div className="z-10 shrink-0">
              <StatusDot status={st.status} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                  {STAGE_TITLE[st.stage] ?? st.stage}
                </span>
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-[10px] font-medium uppercase",
                    st.status === "ok"
                      ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400"
                      : st.status === "fail"
                        ? "bg-rose-50 text-rose-600 dark:bg-rose-950/40 dark:text-rose-400"
                        : "bg-slate-100 text-slate-400 dark:bg-slate-800",
                  )}
                >
                  {st.status}
                </span>
                <span className="tnum text-[11px] text-slate-400">{duration(st.duration_ms)}</span>
                <span className="ml-auto flex items-center gap-1 text-[11px] text-slate-400">
                  {run.actor === "human" ? <User className="h-3 w-3" /> : <Bot className="h-3 w-3" />}
                  {run.actor}
                  <span className="hidden sm:inline">· {dateTime(at)}</span>
                </span>
              </div>
              <KV output={st.output} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}
