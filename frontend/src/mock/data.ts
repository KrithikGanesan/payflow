import type {
  RunRecord,
  StageResult,
  InvoiceExtract,
  DecisionResult,
  Stage,
} from "@/contracts";
import { STAGES } from "@/contracts";

// ── helpers ──────────────────────────────────────────────────────────
function stagesFrom(
  durations: Partial<Record<Stage, number>>,
  outputs: Partial<Record<Stage, Record<string, unknown>>> = {},
  failAt?: Stage,
): StageResult[] {
  let hitFail = false;
  return STAGES.map((s) => {
    const status = hitFail ? "skipped" : failAt === s ? "fail" : "ok";
    if (failAt === s) hitFail = true;
    return {
      stage: s,
      status,
      duration_ms: durations[s] ?? 300,
      output: outputs[s] ?? {},
    };
  });
}

function sum(durations: Partial<Record<Stage, number>>): number {
  return Object.values(durations).reduce((a, b) => a + (b ?? 0), 0);
}

// full-confidence map for a clean extract
const HI = 0.98;

// ── RUN 1 · clean 3-way match → APPROVE ─────────────────────────────
const r1_extract: InvoiceExtract = {
  doc_type: "INVOICE",
  vendor_name: "Meridian Office Supplies",
  vendor_tax_id: "82-4471903",
  vendor_address: "440 Harbor Blvd, Oakland, CA 94607",
  invoice_number: "INV-88213",
  invoice_date: "2026-08-24",
  due_date: "2026-09-23",
  po_number: "PO-40021",
  currency: "USD",
  line_items: [
    { description: 'Ergonomic task chair — "Aria"', quantity: 12, unit_price: 289.0, amount: 3468.0 },
    { description: "Sit-stand desk frame (electric)", quantity: 8, unit_price: 512.5, amount: 4100.0 },
    { description: "Cable management kit", quantity: 20, unit_price: 18.75, amount: 375.0 },
  ],
  subtotal: 7943.0,
  tax_total: 655.3,
  freight: 0,
  discount: 0,
  total: 8598.3,
  payment_terms: "Net 30",
  remit_to_bank: "•••• 4471 — Wells Fargo",
  confidence: {
    vendor_name: HI, invoice_number: HI, invoice_date: 0.97, po_number: HI,
    total: HI, subtotal: HI, tax_total: 0.95, line_items: 0.94,
  },
  validation: { arithmetic_ok: true, po_present: true },
};
const r1_durations: Partial<Record<Stage, number>> = {
  RECEIVED: 120, EXTRACTED: 2140, CODED: 380, MATCHED: 520, VALIDATED: 410, DECIDED: 90,
};
const r1_result: DecisionResult = {
  decision: "APPROVE",
  overall_confidence: 0.96,
  materiality_band: "5k-25k",
  routed_to: "Auto-cleared · Manager DOA ($5k–25k)",
  matched_po: "PO-40021",
  gl_coding: { account: "6420 · Office Furniture & Equipment", cost_center: "CC-200 Facilities", confidence: 0.95 },
  reasons: [
    { code: "MATCH_3WAY_OK", severity: "INFO", rule: "3-way match (PO ↔ invoice ↔ GRN)", message: "3-way match clean: PO-40021, invoice, and goods receipt GRN-7781 all agree on quantity and price.", values: { po: "PO-40021", grn: "GRN-7781", qty_variance: 0, price_variance: 0 } },
    { code: "TOLERANCE_OK", severity: "INFO", rule: "Price/total tolerance ±1% AND ≤ $25", message: "Total $8,598.30 matches PO within tolerance (variance $0.00, 0.0%).", values: { invoice_total: 8598.3, po_total: 8598.3, variance_abs: 0, variance_pct: 0 } },
    { code: "VENDOR_APPROVED", severity: "INFO", rule: "Approved-vendor gate", message: "Vendor 'Meridian Office Supplies' matched vendor master exactly (score 100).", values: { match_score: 100, method: "exact" } },
    { code: "CONFIDENCE_OK", severity: "INFO", rule: "Extraction confidence gate", message: "All critical fields extracted at high confidence (min 0.94).", values: { min_field_confidence: 0.94 } },
  ],
  notifications: [],
};

// ── RUN 2 · tax over-tolerance → HOLD (financial) ───────────────────
const r2_extract: InvoiceExtract = {
  doc_type: "INVOICE",
  vendor_name: "Blue Ridge Freight Co.",
  vendor_tax_id: "45-9982210",
  vendor_address: "17 Depot Rd, Reno, NV 89501",
  invoice_number: "BR-2026-3391",
  invoice_date: "2026-08-26",
  due_date: "2026-09-10",
  po_number: "PO-40088",
  currency: "USD",
  line_items: [
    { description: "LTL freight — pallet ×6", quantity: 6, unit_price: 1500.0, amount: 9000.0 },
    { description: "Fuel surcharge", quantity: 1, unit_price: 1000.0, amount: 1000.0 },
    { description: "Liftgate service", quantity: 1, unit_price: 300.0, amount: 300.0 },
  ],
  subtotal: 10300.0,
  tax_total: 0,
  freight: 0,
  discount: 0,
  total: 10300.0,
  payment_terms: "Net 15",
  remit_to_bank: "•••• 2210 — Chase",
  confidence: {
    vendor_name: 0.96, invoice_number: 0.95, invoice_date: 0.93, po_number: 0.97,
    total: 0.97, subtotal: 0.96, line_items: 0.92,
  },
  validation: { arithmetic_ok: true, po_present: true },
};
const r2_durations: Partial<Record<Stage, number>> = {
  RECEIVED: 110, EXTRACTED: 1980, CODED: 350, MATCHED: 480, VALIDATED: 520, DECIDED: 95,
};
const r2_result: DecisionResult = {
  decision: "HOLD",
  overall_confidence: 0.95,
  materiality_band: "5k-25k",
  routed_to: "Exception queue → Director DOA ($5k–25k)",
  matched_po: "PO-40088",
  gl_coding: { account: "6710 · Freight-In", cost_center: "CC-310 Logistics", confidence: 0.93 },
  reasons: [
    { code: "TOLERANCE_EXCEEDED", severity: "HOLD", rule: "Price/total tolerance ±1% AND ≤ $25", message: "Total $10,300.00 vs PO $10,000.00 = +3.0% (+$300.00) — over ±1% tolerance.", values: { invoice_total: 10300, po_total: 10000, variance_abs: 300, variance_pct: 0.03, tolerance_pct: 0.01 } },
    { code: "VARIANCE_SOURCE", severity: "INFO", rule: "Variance attribution", message: "Variance traced to $300.00 liftgate service not present on PO-40088.", values: { line: "Liftgate service", amount: 300, on_po: false } },
    { code: "MATCH_2WAY_OK", severity: "INFO", rule: "2-way match (services)", message: "Vendor and PO reference valid; services PO requires no goods receipt.", values: { po: "PO-40088", match_type: "2-way" } },
  ],
  notifications: [],
};

// ── RUN 3 · split-PO cumulative over-billing → HOLD ─────────────────
const r3_extract: InvoiceExtract = {
  doc_type: "INVOICE",
  vendor_name: "Kestrel Industrial Parts",
  vendor_tax_id: "91-2237781",
  vendor_address: "2200 Foundry Way, Cleveland, OH 44113",
  invoice_number: "KIP-55240",
  invoice_date: "2026-08-27",
  due_date: "2026-09-26",
  po_number: "PO-39900",
  currency: "USD",
  line_items: [
    { description: "Hydraulic coupler A-12", quantity: 300, unit_price: 42.0, amount: 12600.0 },
    { description: "Seal kit", quantity: 300, unit_price: 6.5, amount: 1950.0 },
  ],
  subtotal: 14550.0,
  tax_total: 1200.4,
  total: 15750.4,
  payment_terms: "Net 30",
  remit_to_bank: "•••• 7781 — PNC",
  confidence: {
    vendor_name: 0.97, invoice_number: 0.96, po_number: 0.98, total: 0.97, line_items: 0.93,
  },
  validation: { arithmetic_ok: true, po_present: true },
};
const r3_durations: Partial<Record<Stage, number>> = {
  RECEIVED: 115, EXTRACTED: 2260, CODED: 360, MATCHED: 610, VALIDATED: 500, DECIDED: 100,
};
const r3_result: DecisionResult = {
  decision: "HOLD",
  overall_confidence: 0.96,
  materiality_band: "5k-25k",
  routed_to: "Exception queue → Director DOA ($5k–25k)",
  matched_po: "PO-39900",
  cumulative_after: 61500.4,
  gl_coding: { account: "5100 · Raw Materials", cost_center: "CC-410 Manufacturing", confidence: 0.94 },
  reasons: [
    { code: "OVERBILL_CUMULATIVE", severity: "HOLD", rule: "Cumulative-billing over-billing guard (split-PO)", message: "This invoice bills $15,750.40; cumulative $61,500.40 would exceed PO-39900 authorized $60,000.00 by $1,500.40.", values: { po_authorized: 60000, billed_prior: 45750, this_invoice: 15750.4, cumulative_after: 61500.4, overage: 1500.4 } },
    { code: "SPLIT_PO_PARTIAL", severity: "INFO", rule: "Split-PO partial billing (stateful)", message: "3rd partial billing against PO-39900 (prior: 2 invoices, $45,750.00).", values: { prior_invoices: 2, prior_total: 45750 } },
    { code: "VENDOR_APPROVED", severity: "INFO", rule: "Approved-vendor gate", message: "Vendor matched vendor master (score 100).", values: { match_score: 100 } },
  ],
  notifications: [],
};

// ── RUN 4 · exact duplicate → REJECT ────────────────────────────────
const r4_extract: InvoiceExtract = {
  doc_type: "INVOICE",
  vendor_name: "Northwind Cloud Services",
  vendor_tax_id: "27-6650012",
  vendor_address: "1 Market St, San Francisco, CA 94105",
  invoice_number: "NW-2026-0412",
  invoice_date: "2026-08-19",
  due_date: "2026-09-18",
  po_number: "PO-40110",
  currency: "USD",
  line_items: [
    { description: "Platform subscription — Aug 2026", quantity: 1, unit_price: 7200.0, amount: 7200.0 },
  ],
  subtotal: 7200.0,
  tax_total: 594.0,
  total: 7794.0,
  payment_terms: "Net 30",
  remit_to_bank: "•••• 0012 — SVB",
  confidence: {
    vendor_name: 0.97, invoice_number: 0.98, total: 0.98, invoice_date: 0.96,
  },
  validation: { arithmetic_ok: true, po_present: true },
};
const r4_durations: Partial<Record<Stage, number>> = {
  RECEIVED: 105, EXTRACTED: 1870, CODED: 0, MATCHED: 0, VALIDATED: 260, DECIDED: 80,
};
const r4_result: DecisionResult = {
  decision: "REJECT",
  overall_confidence: 0.98,
  materiality_band: "5k-25k",
  routed_to: "Blocked — returned to vendor",
  reasons: [
    { code: "DUPLICATE_EXACT", severity: "REJECT", rule: "Duplicate — exact key", message: "Exact duplicate of run VD-1041 (vendor + invoice# NW-2026-0412 + $7,794.00 + date within 2 days). Already paid 2026-08-20.", values: { original_run: "VD-1041", invoice_number: "NW-2026-0412", amount: 7794, original_paid: "2026-08-20", date_proximity_days: 0 } },
  ],
  notifications: [],
};

// ── RUN 5 · scanned / low-confidence → HOLD (graceful degradation) ──
const r5_extract: InvoiceExtract = {
  doc_type: "INVOICE",
  vendor_name: "Sierra Facilities Mgmt",
  vendor_tax_id: undefined,
  vendor_address: "(illegible — scanned)",
  invoice_number: "SF-4471?",
  invoice_date: "2026-08-22",
  po_number: undefined,
  currency: "USD",
  line_items: [
    { description: "Janitorial services — August", quantity: 1, unit_price: 3400.0, amount: 3400.0 },
    { description: "Consumables restock", quantity: 1, unit_price: 612.0, amount: 612.0 },
  ],
  subtotal: 4012.0,
  tax_total: 331.0,
  total: 4343.0,
  payment_terms: "Net 30",
  confidence: {
    vendor_name: 0.71, invoice_number: 0.58, invoice_date: 0.66, total: 0.74,
    subtotal: 0.72, line_items: 0.61,
  },
  validation: { arithmetic_ok: true, po_present: false },
};
const r5_durations: Partial<Record<Stage, number>> = {
  RECEIVED: 130, EXTRACTED: 3410, CODED: 420, MATCHED: 200, VALIDATED: 470, DECIDED: 100,
};
const r5_result: DecisionResult = {
  decision: "HOLD",
  overall_confidence: 0.66,
  materiality_band: "<5k",
  routed_to: "Exception queue → Manager review (OCR verify)",
  gl_coding: { account: "6600 · Facilities Services", cost_center: "CC-200 Facilities", confidence: 0.68 },
  reasons: [
    { code: "LOW_CONFIDENCE", severity: "HOLD", rule: "Extraction confidence gate", message: "Scanned document — invoice number confidence 0.58 (< 0.70). Human OCR verification required before payment.", values: { field: "invoice_number", confidence: 0.58, threshold: 0.7, doc_source: "raster/scanned" } },
    { code: "LOW_CONFIDENCE_CODING", severity: "HOLD", rule: "GL coding confidence", message: "GL account predicted at 0.68 confidence (< 0.70) — no PO to anchor coding.", values: { account: "6600", confidence: 0.68, threshold: 0.7 } },
    { code: "NO_PO", severity: "INFO", rule: "Match", message: "No PO referenced; would route to non-PO approval workflow.", values: { po_present: false } },
  ],
  notifications: [],
};

// ── RUN 6 · PO-bypass under threshold → APPROVE + notify ────────────
const r6_extract: InvoiceExtract = {
  doc_type: "INVOICE",
  vendor_name: "Cedar & Co. Coffee",
  vendor_tax_id: "62-1180043",
  vendor_address: "88 Roastery Ln, Portland, OR 97210",
  invoice_number: "CC-9942",
  invoice_date: "2026-08-28",
  due_date: "2026-09-27",
  po_number: undefined,
  currency: "USD",
  line_items: [
    { description: "Office coffee program — weekly", quantity: 4, unit_price: 78.5, amount: 314.0 },
    { description: "Filters & supplies", quantity: 1, unit_price: 61.0, amount: 61.0 },
  ],
  subtotal: 375.0,
  tax_total: 30.94,
  total: 405.94,
  payment_terms: "Net 30",
  remit_to_bank: "•••• 0043 — US Bank",
  confidence: {
    vendor_name: 0.96, invoice_number: 0.95, total: 0.97, line_items: 0.93,
  },
  validation: { arithmetic_ok: true, po_present: false },
};
const r6_durations: Partial<Record<Stage, number>> = {
  RECEIVED: 100, EXTRACTED: 1760, CODED: 320, MATCHED: 180, VALIDATED: 360, DECIDED: 110,
};
const r6_result: DecisionResult = {
  decision: "APPROVE",
  overall_confidence: 0.95,
  materiality_band: "<5k",
  routed_to: "Auto-cleared — PO-bypass (+ finance notified)",
  gl_coding: { account: "6810 · Office Amenities", cost_center: "CC-100 G&A", confidence: 0.94 },
  reasons: [
    { code: "PO_BYPASS_OK", severity: "INFO", rule: "PO-bypass (< $500, approved vendor, bypass category)", message: "$405.94 under $500 bypass threshold; vendor approved; category 'Office Amenities' eligible. Auto-approved with finance notification.", values: { amount: 405.94, threshold: 500, category: "Office Amenities" } },
    { code: "BYPASS_CAP_OK", severity: "INFO", rule: "Cumulative per-vendor bypass cap", message: "Vendor bypass total this month $1,218.30 of $2,000.00 cap.", values: { month_to_date: 1218.3, cap: 2000 } },
    { code: "VENDOR_APPROVED", severity: "INFO", rule: "Approved-vendor gate", message: "Vendor matched vendor master (score 96, Jaro-Winkler).", values: { match_score: 96 } },
  ],
  notifications: [
    { type: "po_bypass_notify", recipient: "finance-ap@company.com", message: "PO-bypass auto-approval: Cedar & Co. Coffee $405.94 (CC-9942)." },
  ],
};

// ── RUN 7 · spend anomaly → HOLD (fraud instinct) ───────────────────
const r7_extract: InvoiceExtract = {
  doc_type: "INVOICE",
  vendor_name: "Apex Consulting Group",
  vendor_tax_id: "33-7789004",
  vendor_address: "500 Congress Ave, Austin, TX 78701",
  invoice_number: "ACG-2026-118",
  invoice_date: "2026-08-25",
  due_date: "2026-09-24",
  po_number: undefined,
  currency: "USD",
  line_items: [
    { description: "Advisory services — August (retainer)", quantity: 1, unit_price: 48000.0, amount: 48000.0 },
  ],
  subtotal: 48000.0,
  tax_total: 0,
  total: 48000.0,
  payment_terms: "Net 30",
  remit_to_bank: "•••• 9004 — First Republic",
  confidence: {
    vendor_name: 0.96, invoice_number: 0.94, total: 0.97,
  },
  validation: { arithmetic_ok: true, po_present: false },
};
const r7_durations: Partial<Record<Stage, number>> = {
  RECEIVED: 120, EXTRACTED: 1990, CODED: 380, MATCHED: 190, VALIDATED: 640, DECIDED: 120,
};
const r7_result: DecisionResult = {
  decision: "HOLD",
  overall_confidence: 0.96,
  materiality_band: "25k-100k",
  routed_to: "Exception queue → VP DOA ($25k–100k)",
  gl_coding: { account: "7200 · Professional Services", cost_center: "CC-100 G&A", confidence: 0.9 },
  reasons: [
    { code: "SPEND_ANOMALY", severity: "HOLD", rule: "Spend anomaly vs vendor history", message: "$48,000.00 is 6.9× the vendor's trailing-6-month average ($6,950.00). Sudden burst flagged for review.", values: { amount: 48000, trailing_avg: 6950, multiple: 6.9, z_score: 4.2 } },
    { code: "HIGH_MATERIALITY", severity: "INFO", rule: "Materiality band", message: "Amount in $25k–100k band → VP approval per DOA.", values: { band: "25k-100k" } },
    { code: "VENDOR_APPROVED", severity: "INFO", rule: "Approved-vendor gate", message: "Vendor matched vendor master (score 100).", values: { match_score: 100 } },
  ],
  notifications: [],
};

// ── RUN 8 · unapproved vendor + bank change → HOLD (fraud) ──────────
const r8_extract: InvoiceExtract = {
  doc_type: "INVOICE",
  vendor_name: "Meridien Office Supply LLC",
  vendor_tax_id: "82-4471903",
  vendor_address: "440 Harbor Blvd, Oakland, CA 94607",
  invoice_number: "INV-90114",
  invoice_date: "2026-08-27",
  due_date: "2026-09-26",
  po_number: undefined,
  currency: "USD",
  line_items: [
    { description: "Furniture — bulk order", quantity: 1, unit_price: 18400.0, amount: 18400.0 },
  ],
  subtotal: 18400.0,
  tax_total: 1518.0,
  total: 19918.0,
  payment_terms: "Net 30",
  remit_to_bank: "•••• 8890 — Metro CU (NEW)",
  confidence: {
    vendor_name: 0.88, invoice_number: 0.95, total: 0.97, remit_to_bank: 0.92,
  },
  validation: { arithmetic_ok: true, po_present: false },
};
const r8_durations: Partial<Record<Stage, number>> = {
  RECEIVED: 118, EXTRACTED: 2080, CODED: 360, MATCHED: 210, VALIDATED: 700, DECIDED: 130,
};
const r8_result: DecisionResult = {
  decision: "HOLD",
  overall_confidence: 0.9,
  materiality_band: "5k-25k",
  routed_to: "Exception queue → Fraud review (bank-change)",
  gl_coding: { account: "6420 · Office Furniture & Equipment", cost_center: "CC-200 Facilities", confidence: 0.91 },
  reasons: [
    { code: "BANK_DETAIL_CHANGE", severity: "HOLD", rule: "Remit-to bank-detail-change flag", message: "Remit-to bank changed from '•••• 4471 Wells Fargo' (vendor master) to '•••• 8890 Metro CU'. Highest-dollar fraud vector — verify out-of-band.", values: { master_bank: "•••• 4471 Wells Fargo", invoice_bank: "•••• 8890 Metro CU", tax_id_match: true } },
    { code: "VENDOR_FUZZY", severity: "HOLD", rule: "Approved-vendor fuzzy match (80–92 → HOLD)", message: "Name 'Meridien Office Supply LLC' matches 'Meridian Office Supplies' at 87 (Jaro-Winkler) — below 92 auto threshold. Possible look-alike.", values: { match_score: 87, master_name: "Meridian Office Supplies", auto_threshold: 92 } },
  ],
  notifications: [],
};

// ── assemble ─────────────────────────────────────────────────────────
type Seed = {
  id: string; file: string; created: string; actor: string;
  extract: InvoiceExtract; result: DecisionResult;
  durations: Partial<Record<Stage, number>>; failAt?: Stage;
};

const SEEDS: Seed[] = [
  { id: "VD-1052", file: "meridian_INV-88213.pdf", created: "2026-08-29T14:22:10Z", actor: "ai", extract: r1_extract, result: r1_result, durations: r1_durations },
  { id: "VD-1051", file: "blueridge_BR-2026-3391.pdf", created: "2026-08-29T13:05:44Z", actor: "ai", extract: r2_extract, result: r2_result, durations: r2_durations },
  { id: "VD-1050", file: "kestrel_KIP-55240.pdf", created: "2026-08-29T11:48:02Z", actor: "ai", extract: r3_extract, result: r3_result, durations: r3_durations },
  { id: "VD-1049", file: "northwind_NW-2026-0412_dup.pdf", created: "2026-08-29T10:15:36Z", actor: "ai", extract: r4_extract, result: r4_result, durations: r4_durations, failAt: "MATCHED" },
  { id: "VD-1048", file: "sierra_scan_SF-4471.pdf", created: "2026-08-28T16:53:19Z", actor: "ai", extract: r5_extract, result: r5_result, durations: r5_durations },
  { id: "VD-1047", file: "cedar_CC-9942.pdf", created: "2026-08-28T15:20:05Z", actor: "ai", extract: r6_extract, result: r6_result, durations: r6_durations },
  { id: "VD-1046", file: "apex_ACG-2026-118.pdf", created: "2026-08-28T09:41:57Z", actor: "ai", extract: r7_extract, result: r7_result, durations: r7_durations },
  { id: "VD-1045", file: "meridien_INV-90114.pdf", created: "2026-08-27T17:12:28Z", actor: "ai", extract: r8_extract, result: r8_result, durations: r8_durations },
];

function outputsFor(seed: Seed): Partial<Record<Stage, Record<string, unknown>>> {
  const e = seed.extract;
  const r = seed.result;
  return {
    RECEIVED: { file: seed.file, bytes: 184320, doc_type: e.doc_type },
    EXTRACTED: { vendor: e.vendor_name, invoice_number: e.invoice_number, total: e.total, fields: Object.keys(e.confidence).length, min_confidence: Math.min(...Object.values(e.confidence)) },
    CODED: r.gl_coding ? { account: r.gl_coding.account, cost_center: r.gl_coding.cost_center, confidence: r.gl_coding.confidence } : {},
    MATCHED: r.matched_po ? { po: r.matched_po, match_type: r.matched_po.startsWith("PO") ? "matched" : "n/a" } : { po: null },
    VALIDATED: { checks_run: r.reasons.length, worst_severity: r.reasons.some((x) => x.severity === "REJECT") ? "REJECT" : r.reasons.some((x) => x.severity === "HOLD") ? "HOLD" : "INFO" },
    DECIDED: { decision: r.decision, routed_to: r.routed_to, confidence: r.overall_confidence },
  };
}

export const MOCK_RUNS: RunRecord[] = SEEDS.map((seed) => ({
  run_id: seed.id,
  invoice_file: seed.file,
  created_at: seed.created,
  extract: seed.extract,
  result: seed.result,
  stages: stagesFrom(seed.durations, outputsFor(seed), seed.failAt),
  cycle_time_ms: sum(seed.durations),
  actor: seed.actor,
}));

// ── live-run mock sequence ──────────────────────────────────────────
// A fresh invoice processed "live" — the stepper animates through it.
export const LIVE_SEED: Seed = {
  id: "VD-1053",
  file: "orion_lab_OL-77120.pdf",
  created: "2026-08-30T09:00:00Z",
  actor: "ai",
  extract: {
    doc_type: "INVOICE",
    vendor_name: "Orion Lab Reagents",
    vendor_tax_id: "58-2210447",
    vendor_address: "300 Innovation Dr, Cambridge, MA 02139",
    invoice_number: "OL-77120",
    invoice_date: "2026-08-29",
    due_date: "2026-09-28",
    po_number: "PO-40155",
    currency: "USD",
    line_items: [
      { description: "Assay reagent kit (500 rxn)", quantity: 20, unit_price: 410.0, amount: 8200.0 },
      { description: "Calibration standards set", quantity: 4, unit_price: 275.0, amount: 1100.0 },
      { description: "Cold-chain shipping", quantity: 1, unit_price: 240.0, amount: 240.0 },
    ],
    subtotal: 9540.0,
    tax_total: 787.05,
    freight: 240.0,
    total: 10327.05,
    payment_terms: "Net 30",
    remit_to_bank: "•••• 0447 — Citizens",
    confidence: {
      vendor_name: 0.97, invoice_number: 0.96, invoice_date: 0.94, po_number: 0.98,
      total: 0.97, subtotal: 0.96, tax_total: 0.93, line_items: 0.91,
    },
    validation: { arithmetic_ok: true, po_present: true },
  },
  result: {
    decision: "APPROVE",
    overall_confidence: 0.95,
    materiality_band: "5k-25k",
    routed_to: "Auto-cleared · Director DOA ($5k–25k)",
    matched_po: "PO-40155",
    gl_coding: { account: "5150 · Lab Consumables", cost_center: "CC-500 R&D", confidence: 0.94 },
    reasons: [
      { code: "MATCH_3WAY_OK", severity: "INFO", rule: "3-way match (PO ↔ invoice ↔ GRN)", message: "3-way match clean against PO-40155 and goods receipt GRN-7802.", values: { po: "PO-40155", grn: "GRN-7802" } },
      { code: "TOLERANCE_OK", severity: "INFO", rule: "Price/total tolerance ±1% AND ≤ $25", message: "Total $10,327.05 vs PO $10,320.00 = +0.07% (+$7.05) — within tolerance.", values: { variance_abs: 7.05, variance_pct: 0.0007 } },
      { code: "VENDOR_APPROVED", severity: "INFO", rule: "Approved-vendor gate", message: "Vendor matched vendor master (score 100).", values: { match_score: 100 } },
      { code: "CONFIDENCE_OK", severity: "INFO", rule: "Extraction confidence gate", message: "All critical fields high-confidence (min 0.91).", values: { min_field_confidence: 0.91 } },
    ],
    notifications: [],
  },
  durations: { RECEIVED: 140, EXTRACTED: 2200, CODED: 400, MATCHED: 560, VALIDATED: 430, DECIDED: 110 },
};

export function liveRunRecord(): RunRecord {
  return {
    run_id: LIVE_SEED.id,
    invoice_file: LIVE_SEED.file,
    created_at: new Date().toISOString(),
    extract: LIVE_SEED.extract,
    result: LIVE_SEED.result,
    stages: stagesFrom(LIVE_SEED.durations, outputsFor(LIVE_SEED)),
    cycle_time_ms: sum(LIVE_SEED.durations),
    actor: "ai",
  };
}
