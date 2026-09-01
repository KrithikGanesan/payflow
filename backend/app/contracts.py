"""Verdict shared contracts — the data shapes ALL components code against.
Pure schema module: no I/O, no business logic. Backend + agents import from here.
Mirror kept in frontend/src/contracts.ts (must stay in sync)."""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ─────────────────────────── enums ───────────────────────────
class Stage(str, Enum):
    RECEIVED = "RECEIVED"
    EXTRACTED = "EXTRACTED"
    CODED = "CODED"          # GL account + cost centre
    MATCHED = "MATCHED"      # 2-way / 3-way
    VALIDATED = "VALIDATED"  # tolerance, dup, vendor, fraud, anomaly
    DECIDED = "DECIDED"

class Decision(str, Enum):
    APPROVE = "APPROVE"
    HOLD = "HOLD"
    REJECT = "REJECT"

class Severity(str, Enum):
    INFO = "INFO"        # contributes to APPROVE
    HOLD = "HOLD"
    REJECT = "REJECT"

class DocType(str, Enum):
    INVOICE = "INVOICE"
    CREDIT_MEMO = "CREDIT_MEMO"
    STATEMENT = "STATEMENT"
    OTHER = "OTHER"

class ReasonCode(str, Enum):
    # approve
    OK_CLEAN = "OK_CLEAN"; OK_MATCH = "OK_MATCH"; OK_BYPASS = "OK_BYPASS"
    # hold — financial
    HOLD_TOLERANCE = "HOLD_TOLERANCE"; HOLD_OVERBILL = "HOLD_OVERBILL"; HOLD_AWAITING_RECEIPT = "HOLD_AWAITING_RECEIPT"
    HOLD_LOW_CONFIDENCE = "HOLD_LOW_CONFIDENCE"; HOLD_CODING_LOW_CONF = "HOLD_CODING_LOW_CONF"
    HOLD_ANOMALY = "HOLD_ANOMALY"; HOLD_TAX = "HOLD_TAX"; HOLD_CURRENCY = "HOLD_CURRENCY"
    HOLD_CREDIT_MEMO = "HOLD_CREDIT_MEMO"; HOLD_MATERIALITY = "HOLD_MATERIALITY"
    # hold — fraud/compliance
    HOLD_DUP_FUZZY = "HOLD_DUP_FUZZY"; HOLD_VENDOR_FUZZY = "HOLD_VENDOR_FUZZY"
    HOLD_VENDOR_UNAPPROVED = "HOLD_VENDOR_UNAPPROVED"; HOLD_BANK_CHANGE = "HOLD_BANK_CHANGE"
    HOLD_SPLIT_THRESHOLD = "HOLD_SPLIT_THRESHOLD"
    # reject
    REJECT_DUP_EXACT = "REJECT_DUP_EXACT"; REJECT_NO_PO_OVER_BYPASS = "REJECT_NO_PO_OVER_BYPASS"
    REJECT_PO_EXPIRED = "REJECT_PO_EXPIRED"; REJECT_MISSING_CRITICAL = "REJECT_MISSING_CRITICAL"
    REJECT_NOT_INVOICE = "REJECT_NOT_INVOICE"


# ─────────────────────── extraction output ───────────────────────
class LineItem(BaseModel):
    description: str = ""
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    tax_rate: Optional[float] = None

class InvoiceExtract(BaseModel):
    """What the extraction provider returns. Fields nullable — 'return null, never guess'."""
    doc_type: DocType = DocType.INVOICE
    vendor_name: Optional[str] = None
    vendor_tax_id: Optional[str] = None
    vendor_address: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None      # ISO 8601
    due_date: Optional[str] = None
    po_number: Optional[str] = None
    currency: Optional[str] = None          # ISO 4217
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    tax_total: Optional[float] = None
    freight: Optional[float] = None
    discount: Optional[float] = None
    total: Optional[float] = None
    payment_terms: Optional[str] = None     # e.g. "2/10 net 30"
    remit_to_bank: Optional[str] = None     # for bank-change check
    confidence: dict[str, float] = Field(default_factory=dict)   # field -> 0..1
    validation: dict[str, bool] = Field(default_factory=dict)    # line_items_sum_ok, subtotal_plus_tax_ok


# ─────────────────────────── master data ───────────────────────────
class POLine(BaseModel):
    description: str; quantity: float; unit_price: float; line_total: float; uom: str = "EA"

class PurchaseOrder(BaseModel):
    po_number: str; vendor_id: str; currency: str = "USD"
    po_total: float; lines: list[POLine] = Field(default_factory=list)
    status: str = "open"                 # open | closed | expired
    requires_goods_receipt: bool = False # True => 3-way
    cumulative_billed: float = 0.0

class GoodsReceipt(BaseModel):
    gr_id: str; po_number: str; received_total: float; received_date: str

class Vendor(BaseModel):
    vendor_id: str; legal_name: str; normalized_name: str
    tax_id: Optional[str] = None; bank_account_hash: Optional[str] = None
    approved: bool = True; po_bypass_allowed: bool = False; category: str = ""
    default_gl_account: Optional[str] = None; default_cost_center: Optional[str] = None

class HistoricalInvoice(BaseModel):
    vendor_id: str; invoice_number: str; amount: float; invoice_date: str
    line_fingerprint: str = ""


# ─────────────────────── decision output ───────────────────────
class Reason(BaseModel):
    code: ReasonCode; severity: Severity
    message: str                          # plain-English, cites values
    rule: Optional[str] = None            # e.g. "tolerance ±1% AND ≤$25"
    values: dict = Field(default_factory=dict)

class GLCoding(BaseModel):
    account: Optional[str] = None; cost_center: Optional[str] = None; confidence: float = 0.0

class Notification(BaseModel):
    type: str                             # bypass_notice | approver_route | fraud_flag
    recipient: str; message: str

class DecisionResult(BaseModel):
    decision: Decision
    reasons: list[Reason] = Field(default_factory=list)
    overall_confidence: float = 0.0
    materiality_band: str = ""            # <5k | 5k-25k | 25k-100k | >100k
    routed_to: Optional[str] = None
    gl_coding: Optional[GLCoding] = None
    matched_po: Optional[str] = None
    cumulative_after: Optional[float] = None
    notifications: list[Notification] = Field(default_factory=list)

class StageResult(BaseModel):
    stage: Stage; status: str             # ok | fail | skipped
    duration_ms: int = 0; output: dict = Field(default_factory=dict)

class RunRecord(BaseModel):
    run_id: str; invoice_file: str; created_at: str
    extract: Optional[InvoiceExtract] = None
    result: Optional[DecisionResult] = None
    stages: list[StageResult] = Field(default_factory=list)
    cycle_time_ms: int = 0; actor: str = "ai"   # ai | human


# ─────────────────────────── SSE events ───────────────────────────
class SSEEvent(BaseModel):
    type: str                             # stage_started | stage_completed | run_completed
    run_id: str; stage: Optional[Stage] = None
    status: Optional[str] = None; payload: dict = Field(default_factory=dict); ts: str = ""
