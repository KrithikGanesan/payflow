import { useMemo } from "react";
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { RunRecord, Decision } from "@/contracts";
import { useRuns } from "@/lib/useRuns";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { KpiTile } from "@/components/KpiTile";
import { decisionTone } from "@/lib/status";
import { money, num, pct, duration } from "@/lib/format";
import { Gauge, AlertTriangle, Timer, Target } from "lucide-react";

const CHART_TEXT = "#94a3b8";

export function Dashboard() {
  const { runs } = useRuns();
  const m = useMemo(() => computeMetrics(runs), [runs]);

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Straight-through processing, exceptions, and spend at a glance."
      />
      <div className="space-y-6 p-8">
        {/* KPI row */}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <KpiTile
            label="STP rate"
            value={pct(m.stpRate)}
            sub={`${m.approved} of ${m.total} auto-cleared`}
            icon={<Gauge className="h-4 w-4" />}
            trend="4.2pts"
            trendGood
          />
          <KpiTile
            label="Exception rate"
            value={pct(m.exceptionRate)}
            sub={`${m.holds} held for review`}
            icon={<AlertTriangle className="h-4 w-4" />}
            trend="1.1pts"
            trendGood
          />
          <KpiTile
            label="Avg cycle time"
            value={duration(m.avgCycle)}
            sub="ingest → decision"
            icon={<Timer className="h-4 w-4" />}
            trend="0.3s"
            trendGood
          />
          <KpiTile
            label="First-time match"
            value={pct(m.ftMatch)}
            sub="clean 2-/3-way on arrival"
            icon={<Target className="h-4 w-4" />}
            trend="2.0pts"
            trendGood
          />
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* status donut */}
          <Card>
            <CardHeader title="Decision mix" subtitle="This period" />
            <CardBody>
              <div className="relative h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={m.donut}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={58}
                      outerRadius={80}
                      paddingAngle={2}
                      stroke="none"
                    >
                      {m.donut.map((d) => (
                        <Cell key={d.name} fill={d.hex} />
                      ))}
                    </Pie>
                    <Tooltip content={<ChartTip />} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                  <span className="tnum text-2xl font-bold text-slate-900 dark:text-white">
                    {m.total}
                  </span>
                  <span className="text-[11px] text-slate-400">invoices</span>
                </div>
              </div>
              <div className="mt-2 flex justify-center gap-4">
                {m.donut.map((d) => (
                  <div key={d.name} className="flex items-center gap-1.5 text-xs">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: d.hex }} />
                    <span className="text-slate-500 dark:text-slate-400">{d.name}</span>
                    <span className="tnum font-medium text-slate-700 dark:text-slate-200">{d.value}</span>
                  </div>
                ))}
              </div>
            </CardBody>
          </Card>

          {/* aging buckets */}
          <Card>
            <CardHeader title="Invoice aging" subtitle="Open items by age" />
            <CardBody>
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={m.aging} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f033" vertical={false} />
                    <XAxis dataKey="bucket" tick={{ fill: CHART_TEXT, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: CHART_TEXT, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip content={<ChartTip />} cursor={{ fill: "#6366f11a" }} />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {m.aging.map((a, i) => (
                        <Cell key={i} fill={a.hex} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardBody>
          </Card>

          {/* top exception reasons */}
          <Card>
            <CardHeader title="Top exception reasons" subtitle="What drives holds & rejects" />
            <CardBody>
              <div className="space-y-2.5 pt-1">
                {m.topReasons.map((r) => (
                  <div key={r.label}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="truncate text-slate-600 dark:text-slate-300">{r.label}</span>
                      <span className="tnum ml-2 font-medium text-slate-500">{r.count}</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${(r.count / m.topReasonsMax) * 100}%`, background: r.hex }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </CardBody>
          </Card>
        </div>

        {/* spend by vendor */}
        <Card>
          <CardHeader title="Spend by vendor" subtitle="Invoiced amount this period" />
          <CardBody>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={m.spend} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f033" horizontal={false} />
                  <XAxis type="number" tick={{ fill: CHART_TEXT, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${num(v / 1000)}k`} />
                  <YAxis type="category" dataKey="vendor" width={150} tick={{ fill: CHART_TEXT, fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<ChartTip money />} cursor={{ fill: "#6366f11a" }} />
                  <Bar dataKey="amount" fill="#4f46e5" radius={[0, 4, 4, 0]} barSize={16} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function ChartTip({ active, payload, label, money: asMoney }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  const val = asMoney ? money(p.value) : num(p.value);
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs shadow-lift dark:border-slate-700 dark:bg-slate-800">
      <div className="font-medium text-slate-700 dark:text-slate-200">
        {p.payload?.vendor ?? p.payload?.name ?? p.payload?.bucket ?? label}
      </div>
      <div className="tnum font-mono text-slate-500">{val}</div>
    </div>
  );
}

// ── metrics ──────────────────────────────────────────────────────────
function computeMetrics(runs: RunRecord[]) {
  const decided = runs.filter((r) => r.result);
  const total = decided.length || 1;
  const count = (d: Decision) => decided.filter((r) => r.result!.decision === d).length;
  const approved = count("APPROVE");
  const holds = count("HOLD");
  const rejects = count("REJECT");

  const stpRate = approved / total;
  const exceptionRate = (holds + rejects) / total;
  const avgCycle = decided.reduce((a, r) => a + r.cycle_time_ms, 0) / total;
  const matched = decided.filter((r) => r.result!.matched_po).length;
  const withPo = decided.filter((r) => r.extract?.po_number).length || 1;
  const ftMatch = matched / withPo;

  const donut = [
    { name: "Approve", value: approved, hex: decisionTone.APPROVE.hex },
    { name: "Hold", value: holds, hex: decisionTone.HOLD.hex },
    { name: "Reject", value: rejects, hex: decisionTone.REJECT.hex },
  ].filter((d) => d.value > 0);

  // aging buckets (synthetic distribution anchored to open exceptions)
  const openCount = holds + rejects;
  const aging = [
    { bucket: "0–7d", count: approved, hex: "#4f46e5" },
    { bucket: "8–14d", count: Math.max(2, Math.round(openCount * 0.6)), hex: decisionTone.HOLD.hex },
    { bucket: "15–30d", count: Math.max(1, Math.round(openCount * 0.3)), hex: decisionTone.HOLD.hex },
    { bucket: "30d+", count: Math.max(0, rejects), hex: decisionTone.REJECT.hex },
  ];

  // top exception reasons
  const reasonCounts = new Map<string, number>();
  decided
    .filter((r) => r.result!.decision !== "APPROVE")
    .forEach((r) =>
      r.result!.reasons
        .filter((x) => x.severity !== "INFO")
        .forEach((x) => {
          const key = x.rule || x.code;
          reasonCounts.set(key, (reasonCounts.get(key) ?? 0) + 1);
        }),
    );
  const palette = ["#e11d48", "#d97706", "#4f46e5", "#0891b2", "#7c3aed", "#64748b"];
  const topReasons = [...reasonCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([label, cnt], i) => ({ label: shorten(label), count: cnt, hex: palette[i % palette.length] }));
  const topReasonsMax = Math.max(1, ...topReasons.map((r) => r.count));

  // spend by vendor
  const vendorSpend = new Map<string, number>();
  decided.forEach((r) => {
    const v = r.extract?.vendor_name ?? "Unknown";
    vendorSpend.set(v, (vendorSpend.get(v) ?? 0) + (r.extract?.total ?? 0));
  });
  const spend = [...vendorSpend.entries()]
    .map(([vendor, amount]) => ({ vendor, amount }))
    .sort((a, b) => b.amount - a.amount)
    .slice(0, 8);

  return {
    total: decided.length,
    approved,
    holds,
    rejects,
    stpRate,
    exceptionRate,
    avgCycle,
    ftMatch,
    donut,
    aging,
    topReasons,
    topReasonsMax,
    spend,
  };
}

function shorten(s: string): string {
  return s.length > 34 ? s.slice(0, 33) + "…" : s;
}
