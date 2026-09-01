import type { InvoiceExtract } from "@/contracts";
import { money, dateShort } from "@/lib/format";
import { cn } from "@/lib/cn";
import { FileText, ScanLine } from "lucide-react";

/**
 * Renders the source invoice. If a real PDF URL is supplied we embed it;
 * otherwise we render a faithful, styled "paper" facsimile from the extract
 * so the side-by-side always has a credible left pane on mock data.
 */
export function DocumentPreview({
  extract,
  fileUrl,
  fileName,
}: {
  extract?: InvoiceExtract;
  fileUrl?: string;
  fileName?: string;
}) {
  if (fileUrl) {
    return (
      <div className="h-full w-full overflow-hidden rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
        <iframe title="Invoice PDF" src={fileUrl} className="h-full min-h-[560px] w-full" />
      </div>
    );
  }
  if (!extract) {
    return (
      <div className="flex h-full min-h-[560px] items-center justify-center rounded-lg border border-dashed border-slate-300 text-slate-400 dark:border-slate-700">
        <div className="text-center">
          <FileText className="mx-auto h-8 w-8" />
          <p className="mt-2 text-sm">No document yet</p>
        </div>
      </div>
    );
  }

  const scanned = /scan/i.test(fileName ?? "") ||
    Object.values(extract.confidence).some((c) => c < 0.72);

  return (
    <div className="h-full overflow-auto rounded-lg border border-slate-200 bg-slate-100 p-4 dark:border-slate-800 dark:bg-slate-950/60">
      {/* paper */}
      <div
        className={cn(
          "mx-auto max-w-md rounded-md bg-white px-7 py-8 text-slate-800 shadow-lift",
          scanned && "rotate-[-0.35deg] saturate-[0.85] contrast-[0.96]",
        )}
        style={scanned ? { filter: "grayscale(0.15)" } : undefined}
      >
        <div className="flex items-start justify-between border-b border-slate-200 pb-4">
          <div>
            <div className="text-lg font-bold tracking-tight">{extract.vendor_name ?? "—"}</div>
            <div className="mt-0.5 max-w-[16rem] text-[11px] leading-tight text-slate-500">
              {extract.vendor_address}
            </div>
            {extract.vendor_tax_id && (
              <div className="mt-1 font-mono text-[10px] text-slate-400">
                Tax ID {extract.vendor_tax_id}
              </div>
            )}
          </div>
          <div className="text-right">
            <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">
              Invoice
            </div>
            <div className="tnum font-mono text-sm font-semibold">{extract.invoice_number}</div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2 text-[11px]">
          <Field label="Issued" value={dateShort(extract.invoice_date)} />
          <Field label="Due" value={dateShort(extract.due_date)} />
          <Field label="Terms" value={extract.payment_terms ?? "—"} />
          {extract.po_number && <Field label="PO" value={extract.po_number} mono />}
          <Field label="Currency" value={extract.currency ?? "USD"} />
        </div>

        <table className="mt-5 w-full text-[11px]">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-400">
              <th className="pb-1 font-medium">Description</th>
              <th className="pb-1 text-right font-medium">Qty</th>
              <th className="pb-1 text-right font-medium">Unit</th>
              <th className="pb-1 text-right font-medium">Amount</th>
            </tr>
          </thead>
          <tbody>
            {extract.line_items.map((li, i) => (
              <tr key={i} className="border-b border-slate-100">
                <td className="py-1.5 pr-2">{li.description}</td>
                <td className="tnum py-1.5 text-right">{li.quantity ?? "—"}</td>
                <td className="tnum py-1.5 text-right font-mono">
                  {li.unit_price != null ? money(li.unit_price, extract.currency) : "—"}
                </td>
                <td className="tnum py-1.5 text-right font-mono">
                  {li.amount != null ? money(li.amount, extract.currency) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="mt-3 ml-auto w-1/2 space-y-1 text-[11px]">
          <Total label="Subtotal" value={money(extract.subtotal, extract.currency)} />
          {extract.freight ? <Total label="Freight" value={money(extract.freight, extract.currency)} /> : null}
          <Total label="Tax" value={money(extract.tax_total, extract.currency)} />
          <div className="mt-1 flex justify-between border-t border-slate-300 pt-1 text-sm font-bold">
            <span>Total</span>
            <span className="tnum font-mono">{money(extract.total, extract.currency)}</span>
          </div>
        </div>

        {extract.remit_to_bank && (
          <div className="mt-5 rounded border border-slate-200 bg-slate-50 px-3 py-2 text-[10px] text-slate-500">
            Remit to: <span className="font-mono">{extract.remit_to_bank}</span>
          </div>
        )}
      </div>

      <div className="mt-3 flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
        {scanned ? <ScanLine className="h-3.5 w-3.5" /> : <FileText className="h-3.5 w-3.5" />}
        {scanned ? "Rasterised scan — OCR facsimile" : "Rendered from source PDF"}
        {fileName && <span className="font-mono">· {fileName}</span>}
      </div>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className={cn("text-slate-700", mono && "font-mono")}>{value}</div>
    </div>
  );
}

function Total({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-slate-600">
      <span>{label}</span>
      <span className="tnum font-mono">{value}</span>
    </div>
  );
}
