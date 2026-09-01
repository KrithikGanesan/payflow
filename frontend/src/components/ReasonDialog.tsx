import { useEffect, useRef, useState } from "react";
import { Button } from "./ui/Button";
import { cn } from "@/lib/cn";
import { X } from "lucide-react";

const PRESETS: Record<"APPROVE" | "REJECT", string[]> = {
  APPROVE: [
    "Verified against PO — variance is authorized freight",
    "Confirmed with vendor out-of-band; bank change legitimate",
    "Within delegated authority; goods receipt confirmed",
    "OCR fields verified against source scan",
  ],
  REJECT: [
    "Confirmed duplicate — already paid",
    "Vendor not approved; returned for onboarding",
    "Pricing not authorized; sent back to procurement",
    "Suspected fraud — escalated to controller",
  ],
};

export function ReasonDialog({
  open,
  action,
  runLabel,
  onClose,
  onSubmit,
}: {
  open: boolean;
  action: "APPROVE" | "REJECT";
  runLabel: string;
  onClose: () => void;
  onSubmit: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      setReason("");
      setTimeout(() => ref.current?.focus(), 30);
    }
  }, [open, action]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && reason.trim()) {
        onSubmit(reason.trim());
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, reason, onClose, onSubmit]);

  if (!open) return null;
  const isApprove = action === "APPROVE";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md animate-fadein rounded-xl border border-slate-200 bg-white shadow-lift dark:border-slate-700 dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
            {isApprove ? "Approve with reason" : "Reject with reason"}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-3 p-5">
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {isApprove ? "Overriding hold on" : "Rejecting"}{" "}
            <span className="tnum font-mono text-slate-700 dark:text-slate-200">{runLabel}</span>.
            A note is written to the immutable audit trail.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {PRESETS[action].map((p) => (
              <button
                key={p}
                onClick={() => setReason(p)}
                className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] text-slate-500 hover:border-accent hover:text-accent dark:border-slate-700 dark:text-slate-400"
              >
                {p}
              </button>
            ))}
          </div>
          <textarea
            ref={ref}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="Reason for the record…"
            className="w-full resize-none rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
          />
        </div>
        <div className="flex items-center justify-between gap-2 border-t border-slate-200 px-5 py-3 dark:border-slate-800">
          <span className="text-[11px] text-slate-400">
            <span className="kbd">⌘</span> <span className="kbd">↵</span> to submit
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant={isApprove ? "success" : "danger"}
              size="sm"
              disabled={!reason.trim()}
              onClick={() => onSubmit(reason.trim())}
              className={cn(!reason.trim() && "opacity-50")}
            >
              {isApprove ? "Approve" : "Reject"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
