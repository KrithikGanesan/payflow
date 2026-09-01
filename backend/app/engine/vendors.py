"""Approved-vendor gate, fuzzy name match, and remit-to bank-change flag.

- Best-match a vendor from the master by name (rapidfuzz token_set_ratio blended
  with Jaro-Winkler). Bands: ≥92 confident auto-match · 80–92 HOLD for review ·
  <80 no confident match → HOLD as unapproved/ghost vendor.
- Approved-vendor gate: a matched-but-unapproved vendor → HOLD_VENDOR_UNAPPROVED.
- Bank-change flag: remit_to_bank on the invoice ≠ vendor.bank_account_hash on
  file → HOLD_BANK_CHANGE (highest-dollar fraud vector).

Pure: (InvoiceExtract, list[Vendor]) -> (list[Reason], matched Vendor|None).
"""
from __future__ import annotations

from rapidfuzz.distance import JaroWinkler
from rapidfuzz.fuzz import token_set_ratio

from app.contracts import InvoiceExtract, Reason, ReasonCode, Severity, Vendor
from . import config

_RULE_NAME = "vendor name match ≥92 auto / 80–92 HOLD / <80 HOLD"
_RULE_APPROVED = "approved-vendor gate"
_RULE_BANK = "remit-to bank vs vendor master"


def name_score(candidate: str, vendor: Vendor) -> float:
    """Blend token_set_ratio and Jaro-Winkler on a 0..100 scale, best over
    the vendor's normalized and legal names."""
    cand = (candidate or "").strip().lower()
    if not cand:
        return 0.0
    best = 0.0
    for name in (vendor.normalized_name, vendor.legal_name):
        if not name:
            continue
        n = name.strip().lower()
        tsr = token_set_ratio(cand, n)                 # 0..100
        jw = JaroWinkler.similarity(cand, n) * 100.0    # 0..100
        best = max(best, (tsr + jw) / 2.0)
    return round(best, 2)


def match_vendor(extract: InvoiceExtract, vendors: list[Vendor]) -> tuple[Vendor | None, float]:
    best_v, best_s = None, 0.0
    for v in vendors:
        s = name_score(extract.vendor_name, v)
        if s > best_s:
            best_v, best_s = v, s
    return best_v, best_s


def check(extract: InvoiceExtract, vendors: list[Vendor]) -> tuple[list[Reason], Vendor | None]:
    reasons: list[Reason] = []
    best_v, score = match_vendor(extract, vendors or [])

    # No confident match at all → treat as unapproved/ghost vendor.
    if best_v is None or score < config.VENDOR_MATCH_FLOOR:
        reasons.append(Reason(
            code=ReasonCode.HOLD_VENDOR_UNAPPROVED,
            severity=Severity.HOLD,
            message=(f"No approved vendor confidently matches '{extract.vendor_name}' "
                     f"(best score {score:.0f} < {config.VENDOR_MATCH_FLOOR:.0f}); possible "
                     f"unapproved or ghost vendor."),
            rule=_RULE_NAME,
            values={"vendor_name": extract.vendor_name, "score": score},
        ))
        return reasons, best_v if score >= config.VENDOR_MATCH_FLOOR else None

    # We have a candidate at/above the floor.
    if not best_v.approved:
        reasons.append(Reason(
            code=ReasonCode.HOLD_VENDOR_UNAPPROVED,
            severity=Severity.HOLD,
            message=(f"Vendor '{best_v.legal_name}' (matched {score:.0f}) is not approved in the "
                     f"vendor master."),
            rule=_RULE_APPROVED,
            values={"vendor_id": best_v.vendor_id, "score": score, "approved": False},
        ))
    elif score < config.VENDOR_MATCH_AUTO:
        reasons.append(Reason(
            code=ReasonCode.HOLD_VENDOR_FUZZY,
            severity=Severity.HOLD,
            message=(f"Invoice name '{extract.vendor_name}' matches vendor '{best_v.legal_name}' at "
                     f"{score:.0f} ({config.VENDOR_MATCH_FLOOR:.0f}–{config.VENDOR_MATCH_AUTO:.0f} "
                     f"band); confirm identity before payment."),
            rule=_RULE_NAME,
            values={"vendor_id": best_v.vendor_id, "vendor_name": extract.vendor_name, "score": score},
        ))
    else:
        reasons.append(Reason(
            code=ReasonCode.OK_MATCH,
            severity=Severity.INFO,
            message=f"Vendor '{best_v.legal_name}' matched at {score:.0f} (approved).",
            rule=_RULE_NAME,
            values={"vendor_id": best_v.vendor_id, "score": score},
        ))

    # Bank-change flag (independent of the name band).
    if extract.remit_to_bank and best_v.bank_account_hash and extract.remit_to_bank != best_v.bank_account_hash:
        reasons.append(Reason(
            code=ReasonCode.HOLD_BANK_CHANGE,
            severity=Severity.HOLD,
            message=(f"Remit-to bank on invoice differs from vendor '{best_v.legal_name}' master "
                     f"record — verify out-of-band before paying (bank-change fraud vector)."),
            rule=_RULE_BANK,
            values={"vendor_id": best_v.vendor_id, "remit_to_bank": extract.remit_to_bank,
                    "on_file": best_v.bank_account_hash},
        ))

    return reasons, best_v
