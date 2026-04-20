"""
Rule-based triage: certain symptoms automatically trigger high severity.
Returns (severity, True) if a rule matches (then skip LLM), else (None, False).
"""
from typing import Tuple, Optional, Union, List

SEVERITY_1_PHRASES = [
    "cardiac arrest",
    "not breathing",
    "unconscious",
    "stroke",
    "severe bleeding",
]

SEVERITY_2_PHRASES = [
    "chest pain",
    "shortness of breath",
    "severe abdominal pain",
    "confusion",
]


def _normalize(text: str) -> str:
    return text.strip().lower()


def _check_phrases(text: str, phrases: List[str]) -> bool:
    normalized = _normalize(text)
    return any(p in normalized for p in phrases)


def apply_rules(symptoms_input: Union[str, List[str]]) -> Tuple[Optional[int], bool]:
    """
    Check normalized symptom text/list against Severity 1 and Severity 2 phrases.
    Returns (severity, rule_triggered). If rule_triggered is True, use severity and skip LLM.
    """
    if isinstance(symptoms_input, list):
        text = " ".join(symptoms_input)
    else:
        text = str(symptoms_input or "")

    if _check_phrases(text, SEVERITY_1_PHRASES):
        return (1, True)
    if _check_phrases(text, SEVERITY_2_PHRASES):
        return (2, True)
    return (None, False)
