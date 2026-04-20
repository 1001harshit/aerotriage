"""
Ensures safe predictions: if confidence < 0.6 then severity = 2 and flag_for_review = True.
Input: { severity, reasoning, confidence }. Output: same shape plus flag_for_review.
"""
from typing import Dict, Any

CONFIDENCE_THRESHOLD = 0.6


def validate(triage_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    triage_result: { "severity": int, "reasoning": str, "confidence": float }.
    Returns same keys plus "flag_for_review": bool.
    """
    out = dict(triage_result)
    confidence = out.get("confidence")
    if confidence is None:
        confidence = 0.0
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    if confidence < CONFIDENCE_THRESHOLD:
        out["severity"] = 2
        out["flag_for_review"] = True
    else:
        out["flag_for_review"] = False
    return out
