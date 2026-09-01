import type { Decision, Severity } from "@/contracts";

export type ToneClasses = {
  text: string;
  bg: string;
  border: string;
  dot: string;
  solid: string; // solid fill for hero / donut
  hex: string; // raw hex for charts
};

// Status colors are reserved strictly for meaning.
export const decisionTone: Record<Decision, ToneClasses> = {
  APPROVE: {
    text: "text-emerald-700 dark:text-emerald-300",
    bg: "bg-emerald-50 dark:bg-emerald-950/40",
    border: "border-emerald-200 dark:border-emerald-900",
    dot: "bg-emerald-500",
    solid: "bg-emerald-600",
    hex: "#059669",
  },
  HOLD: {
    text: "text-amber-700 dark:text-amber-300",
    bg: "bg-amber-50 dark:bg-amber-950/40",
    border: "border-amber-200 dark:border-amber-900",
    dot: "bg-amber-500",
    solid: "bg-amber-500",
    hex: "#d97706",
  },
  REJECT: {
    text: "text-rose-700 dark:text-rose-300",
    bg: "bg-rose-50 dark:bg-rose-950/40",
    border: "border-rose-200 dark:border-rose-900",
    dot: "bg-rose-500",
    solid: "bg-rose-600",
    hex: "#e11d48",
  },
};

export const decisionLabel: Record<Decision, string> = {
  APPROVE: "Approve",
  HOLD: "Hold",
  REJECT: "Reject",
};

export function decisionVerb(d: Decision): string {
  return d === "APPROVE"
    ? "Cleared for payment"
    : d === "HOLD"
      ? "Routed to exception queue"
      : "Blocked from payment";
}

export type ConfidenceBand = "high" | "medium" | "low";

export function confidenceBand(v: number): ConfidenceBand {
  if (v >= 0.9) return "high";
  if (v >= 0.7) return "medium";
  return "low";
}

export const confidenceTone: Record<ConfidenceBand, ToneClasses> = {
  high: decisionTone.APPROVE,
  medium: decisionTone.HOLD,
  low: decisionTone.REJECT,
};

export const severityTone: Record<Severity, ToneClasses> = {
  INFO: {
    text: "text-slate-600 dark:text-slate-300",
    bg: "bg-slate-100 dark:bg-slate-800/60",
    border: "border-slate-200 dark:border-slate-700",
    dot: "bg-slate-400",
    solid: "bg-slate-500",
    hex: "#64748b",
  },
  HOLD: decisionTone.HOLD,
  REJECT: decisionTone.REJECT,
};
