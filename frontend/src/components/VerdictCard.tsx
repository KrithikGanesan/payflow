import type { DecisionResult } from "@/contracts";
import { decisionTone, decisionLabel, decisionVerb } from "@/lib/status";
import { cn } from "@/lib/cn";
import { pct } from "@/lib/format";
import { CheckCircle2, AlertTriangle, XCircle, Route, Bell } from "lucide-react";
import { ReasonList } from "./ReasonList";

function HeadIcon({ decision }: { decision: DecisionResult["decision"] }) {
  const c = "h-7 w-7";
  if (decision === "APPROVE") return <CheckCircle2 className={c} />;
  if (decision === "HOLD") return <AlertTriangle className={c} />;
  return <XCircle className={c} />;
}

export function VerdictCard({ result }: { result: DecisionResult }) {
  const t = decisionTone[result.decision];
  return (
    <div className={cn("overflow-hidden rounded-xl border shadow-card", t.border)}>
      {/* hero band */}
      <div className={cn("flex items-center gap-4 px-5 py-4", t.solid)}>
        <div className="text-white">
          <HeadIcon decision={result.decision} />
        </div>
        <div className="flex-1 text-white">
          <div className="text-lg font-bold tracking-tight">
            {decisionLabel[result.decision].toUpperCase()}
          </div>
          <div className="text-sm text-white/85">{decisionVerb(result.decision)}</div>
        </div>
        <div className="text-right text-white">
          <div className="tnum text-xl font-bold">{pct(result.overall_confidence)}</div>
          <div className="text-[11px] text-white/80">confidence</div>
        </div>
      </div>

      <div className={cn("space-y-4 px-5 py-4", t.bg)}>
        {/* routing meta */}
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs">
          {result.routed_to && (
            <Meta icon={<Route className="h-3.5 w-3.5" />} label="Routing" value={result.routed_to} />
          )}
          <Meta label="Materiality" value={materialityLabel(result.materiality_band)} />
          {result.matched_po && <Meta label="PO" value={result.matched_po} mono />}
          {result.gl_coding?.account && (
            <Meta label="GL account" value={result.gl_coding.account} mono />
          )}
        </div>

        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Why
          </div>
          <ReasonList reasons={result.reasons} />
        </div>

        {result.notifications.length > 0 && (
          <div className="rounded-lg border border-accent/30 bg-accent-soft px-3 py-2 dark:border-accent/40 dark:bg-accent-softdark/40">
            {result.notifications.map((n, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-accent dark:text-indigo-200">
                <Bell className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  <span className="font-semibold">Notified {n.recipient}:</span> {n.message}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Meta({
  icon,
  label,
  value,
  mono,
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col">
      <span className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
        {icon}
        {label}
      </span>
      <span
        className={cn(
          "text-slate-700 dark:text-slate-200",
          mono && "tnum font-mono text-[13px]",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function materialityLabel(band: string): string {
  switch (band) {
    case "<5k":
      return "Under $5k";
    case "5k-25k":
      return "$5k–25k";
    case "25k-100k":
      return "$25k–100k";
    case ">100k":
      return "Over $100k";
    default:
      return band || "—";
  }
}
