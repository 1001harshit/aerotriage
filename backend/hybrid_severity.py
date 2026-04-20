"""
Hybrid severity system: deterministic base severity from normalized symptom groups
+ red-flag escalation. RAG/LLM is used only for classification into a group and for
consultation time / explanation, not for final severity (stable, medically sensible).
"""
from typing import List, Optional, Tuple

# Normalized symptom groups and example phrases for embedding/keyword classification
NORMALIZED_GROUPS = {
    "fever": ["fever", "high temperature", "feeling hot", "feverish", "temperature", "hot and sweaty", "body aches and fever"],
    "cold_cough": ["cold", "cough", "runny nose", "sneezing", "congestion", "sore throat", "blocked nose", "post nasal drip"],
    "headache": ["headache", "migraine", "head pain", "head hurts", "pounding head"],
    "stomach_pain": ["stomach pain", "abdominal pain", "belly ache", "upset stomach", "bloating", "cramps", "nausea", "indigestion"],
    "chest_pain": ["chest pain", "tight chest", "heart pain", "chest discomfort", "pressure in chest"],
    "breathing_issue": ["difficulty breathing", "shortness of breath", "wheezing", "can't breathe", "out of breath", "breathless"],
    "injury": ["injury", "cut", "bruise", "sprain", "fall", "bleeding", "burn", "fracture", "hit head"],
    "dizziness": ["dizziness", "dizzy", "vertigo", "lightheaded", "faint", "loss of balance"],
    "vomiting": ["vomiting", "vomit", "throwing up", "nausea with vomiting"],
}

# Fixed base severity (1-5) per group. Common symptoms = stable base.
BASE_SEVERITY: dict[str, int] = {
    "fever": 2,
    "cold_cough": 2,
    "headache": 2,
    "stomach_pain": 3,
    "chest_pain": 4,
    "breathing_issue": 4,
    "injury": 3,
    "dizziness": 3,
    "vomiting": 3,
    "general": 3,
}

# Default consultation time (minutes) per group; RAG can refine when text is provided.
CONSULTATION_TIME_MINUTES: dict[str, int] = {
    "fever": 18,
    "cold_cough": 15,
    "headache": 18,
    "stomach_pain": 18,
    "chest_pain": 12,
    "breathing_issue": 12,
    "injury": 15,
    "dizziness": 18,
    "vomiting": 18,
    "general": 20,
}

# Red-flag phrases that escalate severity (checked in order; first match wins).
# Each tuple: (phrase list, severity to set if matched)
RED_FLAG_RULES: List[Tuple[List[str], int]] = [
    (["cardiac arrest", "not breathing", "unconscious", "no pulse", "severe bleeding", "stroke", "unresponsive"], 1),
    (["chest pain", "difficulty breathing", "shortness of breath", "fainting", "fainted", "confusion", "severe bleeding", "can't breathe", "severe abdominal pain", "vomiting blood", "coughing up blood"], 2),
    (["wheezing", "tight chest", "heavy bleeding", "head injury", "hit head", "possible fracture"], 3),
]

MODEL_NAME = "all-MiniLM-L6-v2"
MIN_SIMILARITY = 0.25
DEFAULT_SEVERITY = 3
SEVERITY_MIN = 1
SEVERITY_MAX = 5

_model = None
_phrase_embeddings: Optional[List[Tuple[str, str, List[float]]]] = None


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _get_phrase_embeddings() -> List[Tuple[str, str, List[float]]]:
    """(phrase, group, embedding)."""
    global _phrase_embeddings
    if _phrase_embeddings is not None:
        return _phrase_embeddings
    model = _load_model()
    result = []
    for group, phrases in NORMALIZED_GROUPS.items():
        if not phrases:
            continue
        embs = model.encode(phrases, convert_to_numpy=True)
        for i, phrase in enumerate(phrases):
            result.append((phrase, group, embs[i].tolist()))
    _phrase_embeddings = result
    return result


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _keyword_match(text: str) -> Optional[str]:
    t = (text or "").strip().lower()
    if not t:
        return None
    for group, phrases in NORMALIZED_GROUPS.items():
        for phrase in phrases:
            if phrase.lower() in t:
                return group
    return None


def get_symptom_group(text: str) -> str:
    """
    Map free-text symptoms to the closest normalized group.
    Uses embedding similarity; falls back to keyword match. Deterministic.
    """
    text = (text or "").strip()
    if not text:
        return "general"

    kw = _keyword_match(text)
    if kw:
        return kw

    try:
        model = _load_model()
        phrase_embs = _get_phrase_embeddings()
        text_emb = model.encode([text], convert_to_numpy=True)[0].tolist()
        best_group = "general"
        best_sim = MIN_SIMILARITY
        for _phrase, group, pemb in phrase_embs:
            sim = _cosine_similarity(text_emb, pemb)
            if sim > best_sim:
                best_sim = sim
                best_group = group
        return best_group
    except Exception:
        pass
    return "general"


def get_base_severity(group: str) -> int:
    """Return fixed base severity (1-5) for a normalized group."""
    return BASE_SEVERITY.get(group, DEFAULT_SEVERITY)


def apply_red_flag_rules(text: str, base_severity: int) -> int:
    """
    If text contains dangerous indicators, return the escalated severity; else base_severity.
    Final value is clamped between 1 and 5.
    """
    t = (text or "").strip().lower()
    if not t:
        return max(SEVERITY_MIN, min(SEVERITY_MAX, base_severity))

    for phrases, severity in RED_FLAG_RULES:
        if any(p in t for p in phrases):
            return max(SEVERITY_MIN, min(SEVERITY_MAX, severity))
    return max(SEVERITY_MIN, min(SEVERITY_MAX, base_severity))


def compute_severity(text: str) -> Tuple[int, str]:
    """
    Deterministic severity from group + red flags.
    Returns (severity 1-5, normalized_group).
    """
    group = get_symptom_group(text)
    base = get_base_severity(group)
    final = apply_red_flag_rules(text, base)
    return final, group


def estimate_consultation_time(text: Optional[str] = None, group: Optional[str] = None) -> Tuple[float, str]:
    """
    Estimated consultation time in minutes. Uses RAG when text is provided; else fixed time per group.
    Returns (minutes, normalized_group).
    """
    if text and (text or "").strip():
        try:
            from backend.rag_expected_time import get_expected_time_from_rag
            minutes, rag_group = get_expected_time_from_rag(text)
            return float(minutes), rag_group
        except Exception:
            pass
    g = (group or "general").strip() or "general"
    return float(CONSULTATION_TIME_MINUTES.get(g, CONSULTATION_TIME_MINUTES["general"])), g
