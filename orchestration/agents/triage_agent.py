"""
Triage: deterministic severity from hybrid_severity (normalized group + red-flag rules).
RAG is used only for similar-case retrieval, consultation time, and optional explanation—
not as the direct source of final severity (stable, medically sensible).
"""
from typing import Any, Dict, List, Union


def triage(symptoms: Union[str, List[str]]) -> Dict[str, Any]:
    """
    Returns dict: { "severity": 1-5, "reasoning": str, "confidence": 0.9, "rag_sources": list }.
    Severity is from hybrid_severity (group base + red-flag escalation). Same input -> same severity.
    """
    if isinstance(symptoms, list):
        symptoms_text = ", ".join(symptoms)
    else:
        symptoms_text = str(symptoms or "").strip()

    from backend.hybrid_severity import (
        get_symptom_group,
        get_base_severity,
        apply_red_flag_rules,
        compute_severity,
    )
    from ai_core.rag.retriever import retrieve_sources

    severity, group = compute_severity(symptoms_text)
    base = get_base_severity(group)
    reasoning = _build_reasoning(group, base, severity, symptoms_text)

    rag_sources = []
    try:
        rag_sources = retrieve_sources(symptoms_text)
    except Exception:
        pass

    return {
        "severity": severity,
        "reasoning": reasoning,
        "confidence": 0.9,
        "flag_for_review": False,
        "rag_sources": rag_sources,
        "symptom_group": group,
    }


def _build_reasoning(group: str, base_severity: int, final_severity: int, text: str) -> str:
    """Deterministic explanation: group + red-flag escalation if applied."""
    group_label = group.replace("_", " ").title()
    if final_severity == base_severity:
        return f"Group: {group_label}. Base severity {base_severity}. No red flags."
    return f"Group: {group_label}. Base severity {base_severity}; red-flag escalation -> {final_severity}."
