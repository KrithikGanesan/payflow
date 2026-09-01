// Maps a completed DecisionResult → an ordered list of decision-flow nodes
// (the gates), each with a state + the numbers it compared. Pure + testable.
import type { DecisionResult, Reason, Severity } from "@/contracts";

export type FlowState = "pending" | "active" | "pass" | "hold" | "reject" | "skipped";

export interface FlowNodeVM {
  id: string;
  label: string;
  state: FlowState;
  reasons: Reason[];
  chips: { k: string; v: string }[];
  driving: boolean;
}

interface Ctx { earlyReject: boolean; hasPO: boolean; creditMemo: boolean; }
interface NodeDef {
  id: string; label: string; codes: string[];
  okMatch?: (rule: string) => boolean;   // which OK_MATCH belongs to this node
  skip: (c: Ctx) => boolean;
}

const NODES: NodeDef[] = [
  { id: "intake",     label: "Intake / Document",       codes: ["REJECT_NOT_INVOICE", "REJECT_MISSING_CRITICAL", "HOLD_CREDIT_MEMO"], skip: () => false },
  { id: "vendor",     label: "Vendor",                  codes: ["HOLD_VENDOR_UNAPPROVED", "HOLD_VENDOR_FUZZY", "HOLD_BANK_CHANGE", "OK_MATCH"], okMatch: (r) => /vendor/i.test(r), skip: (c) => c.earlyReject },
  { id: "coding",     label: "GL Coding",               codes: ["HOLD_CODING_LOW_CONF"], skip: (c) => c.earlyReject },
  { id: "confidence", label: "Confidence & Arithmetic", codes: ["HOLD_LOW_CONFIDENCE"], skip: (c) => c.earlyReject },
  { id: "po",         label: "PO & Currency",           codes: ["REJECT_PO_EXPIRED", "HOLD_CURRENCY"], skip: (c) => c.earlyReject || !c.hasPO },
  { id: "dup",        label: "Duplicates",              codes: ["REJECT_DUP_EXACT", "HOLD_DUP_FUZZY"], skip: (c) => c.earlyReject },
  { id: "match",      label: "Matching & Tolerance",    codes: ["HOLD_OVERBILL", "HOLD_AWAITING_RECEIPT", "HOLD_TOLERANCE", "OK_MATCH"], okMatch: (r) => /tolerance|match/i.test(r), skip: (c) => c.earlyReject || c.creditMemo || !c.hasPO },
  { id: "bypass",     label: "PO-Bypass / No-PO",       codes: ["OK_BYPASS", "REJECT_NO_PO_OVER_BYPASS", "HOLD_MATERIALITY"], skip: (c) => c.earlyReject || c.creditMemo || c.hasPO },
  { id: "anomaly",    label: "Anomaly & Split",         codes: ["HOLD_ANOMALY", "HOLD_SPLIT_THRESHOLD"], skip: (c) => c.earlyReject || c.creditMemo },
];

const sevRank = (s: Severity): number => (s === "REJECT" ? 3 : s === "HOLD" ? 2 : 1);

function chipsFor(reasons: Reason[], result: DecisionResult, id: string): { k: string; v: string }[] {
  const chips: { k: string; v: string }[] = [];
  if (id === "coding" && result.gl_coding) {
    const g = result.gl_coding;
    if (g.account) chips.push({ k: "account", v: String(g.account) });
    if (g.cost_center) chips.push({ k: "cost ctr", v: String(g.cost_center) });
    if (typeof g.confidence === "number") chips.push({ k: "conf", v: (g.confidence * 100).toFixed(0) + "%" });
  }
  for (const r of reasons) {
    for (const [k, v] of Object.entries(r.values || {})) {
      if (v === null || v === undefined || typeof v === "object") continue;
      chips.push({ k, v: String(v) });
    }
  }
  return chips.slice(0, 6);
}

export function deriveNodes(result: DecisionResult): FlowNodeVM[] {
  const reasons = result.reasons || [];
  const has = (code: string) => reasons.some((r) => r.code === code);
  const ctx: Ctx = {
    earlyReject: has("REJECT_NOT_INVOICE") || has("REJECT_MISSING_CRITICAL"),
    hasPO: !!result.matched_po,
    creditMemo: has("HOLD_CREDIT_MEMO"),
  };
  const decRank = result.decision === "REJECT" ? 3 : result.decision === "HOLD" ? 2 : 1;

  return NODES.map((def) => {
    const owned = reasons.filter((r) => {
      if (!def.codes.includes(r.code)) return false;
      if (r.code === "OK_MATCH" && def.okMatch) return def.okMatch(r.rule || "");
      return true;
    });
    let state: FlowState;
    if (def.skip(ctx)) state = "skipped";
    else if (owned.some((r) => r.severity === "REJECT")) state = "reject";
    else if (owned.some((r) => r.severity === "HOLD")) state = "hold";
    else state = "pass";
    const driving = state !== "skipped" && owned.some((r) => r.severity !== "INFO" && sevRank(r.severity) === decRank);
    return { id: def.id, label: def.label, state, reasons: owned, chips: chipsFor(owned, result, def.id), driving };
  });
}
