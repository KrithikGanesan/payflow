import { confidenceBand, confidenceTone } from "@/lib/status";
import { cn } from "@/lib/cn";

export function ConfidenceBadge({
  value,
  showValue = true,
  className,
}: {
  value: number;
  showValue?: boolean;
  className?: string;
}) {
  const band = confidenceBand(value);
  const t = confidenceTone[band];
  return (
    <span
      title={`Confidence ${(value * 100).toFixed(0)}% — ${band}`}
      className={cn(
        "tnum inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium",
        t.bg,
        t.text,
        t.border,
        className,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", t.dot)} />
      {showValue ? `${(value * 100).toFixed(0)}%` : null}
    </span>
  );
}
