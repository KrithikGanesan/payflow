import type { Decision } from "@/contracts";
import { decisionTone, decisionLabel } from "@/lib/status";
import { cn } from "@/lib/cn";

export function StatusPill({
  decision,
  size = "md",
}: {
  decision: Decision;
  size?: "sm" | "md";
}) {
  const t = decisionTone[decision];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border font-medium",
        t.bg,
        t.text,
        t.border,
        size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", t.dot)} />
      {decisionLabel[decision]}
    </span>
  );
}
