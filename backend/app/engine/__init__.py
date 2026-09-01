"""Verdict decision engine — pure, I/O-free rule functions.

Public surface:
    decide.decide(extract, vendors, po, goods_receipt, historical_invoices) -> DecisionResult

Individual gates (all pure, all return list[Reason] unless noted):
    matching · tolerance · duplicates · vendors · coding · anomaly · policy
Thresholds live in `config`.
"""
from . import anomaly, coding, config, decide, duplicates, matching, policy, tolerance, vendors

__all__ = [
    "anomaly", "coding", "config", "decide", "duplicates",
    "matching", "policy", "tolerance", "vendors",
]
