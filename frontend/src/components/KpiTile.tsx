import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";

export function KpiTile({
  label,
  value,
  sub,
  icon,
  trend,
  trendGood,
}: {
  label: string;
  value: string;
  sub?: string;
  icon?: ReactNode;
  trend?: string;
  trendGood?: boolean;
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</span>
        {icon && (
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-soft text-accent dark:bg-accent-softdark/50 dark:text-indigo-300">
            {icon}
          </span>
        )}
      </div>
      <div className="mt-2 flex items-end gap-2">
        <span className="tnum text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-50">
          {value}
        </span>
        {trend && (
          <span
            className={cn(
              "mb-1 inline-flex items-center gap-0.5 text-xs font-medium",
              trendGood
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-rose-600 dark:text-rose-400",
            )}
          >
            {trendGood ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
            {trend}
          </span>
        )}
      </div>
      {sub && <div className="mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">{sub}</div>}
    </div>
  );
}
