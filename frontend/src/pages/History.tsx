import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { RunRecord, Decision } from "@/contracts";
import { useRuns } from "@/lib/useRuns";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/StatusPill";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { money, duration, dateShort } from "@/lib/format";
import { cn } from "@/lib/cn";
import { ArrowUpDown, ArrowUp, ArrowDown, Search } from "lucide-react";

type SortKey = "invoice" | "vendor" | "amount" | "status" | "confidence" | "cycle" | "date";
type Dir = "asc" | "desc";

const STATUS_ORDER: Record<Decision, number> = { APPROVE: 0, HOLD: 1, REJECT: 2 };

export function History() {
  const { runs } = useRuns();
  const nav = useNavigate();
  const [sort, setSort] = useState<SortKey>("date");
  const [dir, setDir] = useState<Dir>("desc");
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Decision | "ALL">("ALL");

  const toggle = (k: SortKey) => {
    if (sort === k) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSort(k);
      setDir("asc");
    }
  };

  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    let out = runs.filter((r) => r.result);
    if (filter !== "ALL") out = out.filter((r) => r.result!.decision === filter);
    if (term)
      out = out.filter(
        (r) =>
          r.extract?.vendor_name?.toLowerCase().includes(term) ||
          r.extract?.invoice_number?.toLowerCase().includes(term) ||
          r.run_id.toLowerCase().includes(term),
      );
    const val = (r: RunRecord): number | string => {
      switch (sort) {
        case "invoice": return r.extract?.invoice_number ?? "";
        case "vendor": return r.extract?.vendor_name ?? "";
        case "amount": return r.extract?.total ?? 0;
        case "status": return STATUS_ORDER[r.result!.decision];
        case "confidence": return r.result!.overall_confidence;
        case "cycle": return r.cycle_time_ms;
        case "date": return new Date(r.created_at).getTime();
      }
    };
    return [...out].sort((a, b) => {
      const av = val(a), bv = val(b);
      const cmp = typeof av === "number" && typeof bv === "number"
        ? av - bv
        : String(av).localeCompare(String(bv));
      return dir === "asc" ? cmp : -cmp;
    });
  }, [runs, sort, dir, q, filter]);

  return (
    <div>
      <PageHeader
        title="History"
        subtitle="Every processed invoice with its decision and cycle time."
        actions={
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search vendor, invoice #…"
              className="h-9 w-64 rounded-lg border border-slate-300 bg-white pl-8 pr-3 text-sm text-slate-700 placeholder:text-slate-400 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
            />
          </div>
        }
      />

      <div className="space-y-4 p-8">
        <div className="flex gap-1.5">
          {(["ALL", "APPROVE", "HOLD", "REJECT"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                filter === f
                  ? "bg-accent text-white"
                  : "border border-slate-200 text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800",
              )}
            >
              {f === "ALL" ? "All" : f.charAt(0) + f.slice(1).toLowerCase()}
            </button>
          ))}
          <span className="ml-auto self-center text-xs text-slate-400">{rows.length} records</span>
        </div>

        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/60 text-left dark:border-slate-800 dark:bg-slate-900/40">
                  <Th label="Invoice" k="invoice" sort={sort} dir={dir} onSort={toggle} />
                  <Th label="Vendor" k="vendor" sort={sort} dir={dir} onSort={toggle} />
                  <Th label="Amount" k="amount" sort={sort} dir={dir} onSort={toggle} align="right" />
                  <Th label="Status" k="status" sort={sort} dir={dir} onSort={toggle} />
                  <Th label="Confidence" k="confidence" sort={sort} dir={dir} onSort={toggle} />
                  <Th label="Cycle" k="cycle" sort={sort} dir={dir} onSort={toggle} align="right" />
                  <Th label="Date" k="date" sort={sort} dir={dir} onSort={toggle} align="right" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {rows.map((r) => (
                  <tr
                    key={r.run_id}
                    onClick={() => nav(`/runs/${r.run_id}`)}
                    className="cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
                  >
                    <td className="px-4 py-3">
                      <div className="tnum font-mono text-slate-800 dark:text-slate-100">
                        {r.extract?.invoice_number ?? "—"}
                      </div>
                      <div className="tnum font-mono text-[11px] text-slate-400">{r.run_id}</div>
                    </td>
                    <td className="px-4 py-3 text-slate-700 dark:text-slate-200">
                      {r.extract?.vendor_name ?? "—"}
                    </td>
                    <td className="tnum px-4 py-3 text-right font-mono font-medium text-slate-800 dark:text-slate-100">
                      {money(r.extract?.total, r.extract?.currency)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill decision={r.result!.decision} size="sm" />
                    </td>
                    <td className="px-4 py-3">
                      <ConfidenceBadge value={r.result!.overall_confidence} />
                    </td>
                    <td className="tnum px-4 py-3 text-right font-mono text-slate-500">
                      {duration(r.cycle_time_ms)}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-500">{dateShort(r.created_at)}</td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-sm text-slate-400">
                      No matching invoices.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}

function Th({
  label,
  k,
  sort,
  dir,
  onSort,
  align = "left",
}: {
  label: string;
  k: SortKey;
  sort: SortKey;
  dir: Dir;
  onSort: (k: SortKey) => void;
  align?: "left" | "right";
}) {
  const active = sort === k;
  return (
    <th className={cn("px-4 py-2.5", align === "right" && "text-right")}>
      <button
        onClick={() => onSort(k)}
        className={cn(
          "inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide",
          active ? "text-slate-700 dark:text-slate-200" : "text-slate-400 hover:text-slate-600 dark:hover:text-slate-300",
          align === "right" && "flex-row-reverse",
        )}
      >
        {label}
        {active ? (
          dir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-50" />
        )}
      </button>
    </th>
  );
}
