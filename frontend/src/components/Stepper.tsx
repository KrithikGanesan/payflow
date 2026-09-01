import { STAGES } from "@/contracts";
import type { Stage } from "@/contracts";
import { cn } from "@/lib/cn";
import { Check, X, Loader2 } from "lucide-react";

export type StageState = "pending" | "running" | "done" | "failed" | "skipped";

const LABELS: Record<Stage, string> = {
  RECEIVED: "Received",
  EXTRACTED: "Extracted",
  CODED: "Coded",
  MATCHED: "Matched",
  VALIDATED: "Validated",
  DECIDED: "Decided",
};

const SUBS: Record<Stage, string> = {
  RECEIVED: "Ingest & hash",
  EXTRACTED: "Vision + text",
  CODED: "GL + cost centre",
  MATCHED: "PO ↔ GRN",
  VALIDATED: "Gates & checks",
  DECIDED: "Decision + route",
};

export function Stepper({
  states,
  durations,
}: {
  states: Record<Stage, StageState>;
  durations?: Partial<Record<Stage, number>>;
}) {
  return (
    <ol className="flex w-full items-start">
      {STAGES.map((stage, i) => {
        const state = states[stage];
        const isLast = i === STAGES.length - 1;
        return (
          <li key={stage} className="flex flex-1 flex-col items-center">
            <div className="flex w-full items-center">
              {/* left connector */}
              <div
                className={cn(
                  "h-0.5 flex-1",
                  i === 0
                    ? "opacity-0"
                    : connectorClass(states[STAGES[i - 1]], state),
                )}
              />
              <StageNode stage={stage} state={state} index={i} />
              {/* right connector */}
              <div
                className={cn(
                  "h-0.5 flex-1",
                  isLast ? "opacity-0" : connectorClass(state, states[STAGES[i + 1]]),
                )}
              />
            </div>
            <div className="mt-2 text-center">
              <div
                className={cn(
                  "text-xs font-semibold",
                  state === "pending"
                    ? "text-slate-400 dark:text-slate-500"
                    : state === "failed"
                      ? "text-rose-600 dark:text-rose-400"
                      : "text-slate-800 dark:text-slate-100",
                )}
              >
                {LABELS[stage]}
              </div>
              <div className="mt-0.5 hidden text-[11px] text-slate-400 sm:block dark:text-slate-500">
                {state === "running"
                  ? "processing…"
                  : (state === "done" || state === "failed") && durations?.[stage]
                    ? `${((durations[stage] ?? 0) / 1000).toFixed(1)}s`
                    : SUBS[stage]}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function connectorClass(prev: StageState, _next: StageState): string {
  return prev === "done" || prev === "failed"
    ? "bg-accent"
    : "bg-slate-200 dark:bg-slate-700";
}

function StageNode({
  stage,
  state,
  index,
}: {
  stage: Stage;
  state: StageState;
  index: number;
}) {
  const common =
    "relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 text-xs font-semibold transition-colors";
  if (state === "done")
    return (
      <div className={cn(common, "border-accent bg-accent text-white")} aria-label={`${stage} done`}>
        <Check className="h-4 w-4" strokeWidth={3} />
      </div>
    );
  if (state === "failed")
    return (
      <div className={cn(common, "border-rose-500 bg-rose-500 text-white")} aria-label={`${stage} failed`}>
        <X className="h-4 w-4" strokeWidth={3} />
      </div>
    );
  if (state === "running")
    return (
      <div
        className={cn(
          common,
          "animate-pulsering border-accent bg-accent/10 text-accent dark:bg-accent/20",
        )}
        aria-label={`${stage} running`}
      >
        <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2.5} />
      </div>
    );
  if (state === "skipped")
    return (
      <div
        className={cn(common, "border-slate-200 bg-slate-100 text-slate-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-600")}
        aria-label={`${stage} skipped`}
      >
        –
      </div>
    );
  return (
    <div
      className={cn(
        common,
        "border-slate-300 bg-white text-slate-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-500",
      )}
      aria-label={`${stage} pending`}
    >
      {index + 1}
    </div>
  );
}
