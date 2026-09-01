// Verdict shared contracts — MIRROR of backend/app/contracts.py. Keep in sync.
export type Stage = "RECEIVED"|"EXTRACTED"|"CODED"|"MATCHED"|"VALIDATED"|"DECIDED";
export const STAGES: Stage[] = ["RECEIVED","EXTRACTED","CODED","MATCHED","VALIDATED","DECIDED"];
export type Decision = "APPROVE"|"HOLD"|"REJECT";
export type Severity = "INFO"|"HOLD"|"REJECT";
export type DocType = "INVOICE"|"CREDIT_MEMO"|"STATEMENT"|"OTHER";

export interface LineItem { description:string; quantity?:number; unit_price?:number; amount?:number; tax_rate?:number; }
export interface InvoiceExtract {
  doc_type:DocType; vendor_name?:string; vendor_tax_id?:string; vendor_address?:string;
  invoice_number?:string; invoice_date?:string; due_date?:string; po_number?:string;
  currency?:string; line_items:LineItem[];
  subtotal?:number; tax_total?:number; freight?:number; discount?:number; total?:number;
  payment_terms?:string; remit_to_bank?:string;
  confidence:Record<string,number>; validation:Record<string,boolean>;
}
export interface Reason { code:string; severity:Severity; message:string; rule?:string; values:Record<string,unknown>; }
export interface GLCoding { account?:string; cost_center?:string; confidence:number; }
export interface Notification { type:string; recipient:string; message:string; }
export interface DecisionResult {
  decision:Decision; reasons:Reason[]; overall_confidence:number; materiality_band:string;
  routed_to?:string; gl_coding?:GLCoding; matched_po?:string; cumulative_after?:number;
  notifications:Notification[];
}
export interface StageResult { stage:Stage; status:string; duration_ms:number; output:Record<string,unknown>; }
export interface RunRecord {
  run_id:string; invoice_file:string; created_at:string;
  extract?:InvoiceExtract; result?:DecisionResult; stages:StageResult[];
  cycle_time_ms:number; actor:string;
}
export interface SSEEvent { type:string; run_id:string; stage?:Stage; status?:string; payload:Record<string,unknown>; ts:string; }
