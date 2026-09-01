import type { InvoiceExtract } from "@/contracts";
import { money, dateShort } from "@/lib/format";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { cn } from "@/lib/cn";

type Row = { key: string; label: string; value: string; mono?: boolean };

export function ExtractedFields({ extract }: { extract?: InvoiceExtract }) {
  if (!extract) {
    return (
      <div className="flex h-full min-h-[200px] items-center justify-center text-sm text-slate-400">
        Fields appear once extraction completes.
      </div>
    );
  }
  const c = extract.confidence;
  const rows: Row[] = [
    { key: "vendor_name", label: "Vendor", value: extract.vendor_name ?? "—" },
    { key: "invoice_number", label: "Invoice #", value: extract.invoice_number ?? "—", mono: true },
    { key: "po_number", label: "PO #", value: extract.po_number ?? "— none —", mono: true },
    { key: "invoice_date", label: "Invoice date", value: dateShort(extract.invoice_date) },
    { key: "subtotal", label: "Subtotal", value: money(extract.subtotal, extract.currency), mono: true },
    { key: "tax_total", label: "Tax", value: money(extract.tax_total, extract.currency), mono: true },
    { key: "total", label: "Total", value: money(extract.total, extract.currency), mono: true },
  ];

  return (
    <div className="space-y-4">
      <dl className="divide-y divide-slate-100 dark:divide-slate-800">
        {rows.map((r) => (
          <div key={r.key} className="flex items-center justify-between gap-3 py-2">
            <dt className="text-xs font-medium text-slate-500 dark:text-slate-400">
              {r.label}
            </dt>
            <dd className="flex items-center gap-2">
              <span
                className={cn(
                  "text-sm text-slate-800 dark:text-slate-100",
                  r.mono && "tnum font-mono",
                  r.key === "total" && "font-semibold",
                )}
              >
                {r.value}
              </span>
              {c[r.key] != null && <ConfidenceBadge value={c[r.key]} />}
            </dd>
          </div>
        ))}
      </dl>

      <div>
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
          Line items · {extract.line_items.length}
          {c.line_items != null && (
            <ConfidenceBadge value={c.line_items} className="ml-2 align-middle" />
          )}
        </div>
        <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800">
          <table className="w-full text-xs">
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {extract.line_items.map((li, i) => (
                <tr key={i}>
                  <td className="px-2.5 py-1.5 text-slate-700 dark:text-slate-200">
                    {li.description}
                  </td>
                  <td className="tnum px-2.5 py-1.5 text-right font-mono text-slate-500">
                    ×{li.quantity ?? "—"}
                  </td>
                  <td className="tnum px-2.5 py-1.5 text-right font-mono text-slate-800 dark:text-slate-100">
                    {li.amount != null ? money(li.amount, extract.currency) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
