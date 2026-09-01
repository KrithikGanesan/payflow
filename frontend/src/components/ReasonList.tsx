import type { Reason } from "@/contracts";
import { severityTone } from "@/lib/status";
import { cn } from "@/lib/cn";
import { AlertTriangle, Ban, Info } from "lucide-react";

function icon(sev: Reason["severity"]) {
  if (sev === "REJECT") return <Ban className="h-4 w-4" />;
  if (sev === "HOLD") return <AlertTriangle className="h-4 w-4" />;
  return <Info className="h-4 w-4" />;
}

export function ReasonList({ reasons }: { reasons: Reason[] }) {
  // Most-severe first so the driving reason reads at the top.
  const order = { REJECT: 0, HOLD: 1, INFO: 2 } as const;
  const sorted = [...reasons].sort((a, b) => order[a.severity] - order[b.severity]);
  return (
    <ul className="space-y-2.5">
      {sorted.map((r, i) => {
        const t = severityTone[r.severity];
        return (
          <li
            key={`${r.code}-${i}`}
            className={cn(
              "flex gap-3 rounded-lg border p-3",
              t.bg,
              t.border,
            )}
          >
            <span className={cn("mt-0.5 shrink-0", t.text)}>{icon(r.severity)}</span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className={cn("text-sm font-semibold", t.text)}>
                  {r.severity === "INFO" ? "Passed" : r.severity === "HOLD" ? "Hold" : "Reject"}
                </span>
                {r.rule && (
                  <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                    {r.rule}
                  </span>
                )}
                <code className="tnum rounded bg-slate-200/60 px-1 text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                  {r.code}
                </code>
              </div>
              <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">
                {r.message}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
