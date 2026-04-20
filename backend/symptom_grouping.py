"""
Symptom grouping: map free-text symptoms to normalized groups and group-based average wait times.
Uses sentence-transformers for embedding-based match with keyword fallback.
"""
from typing import List, Optional, Tuple

# Symptom groups with example phrases for embedding and keyword match
SYMPTOM_GROUPS = {
    "fever": ["fever", "high temperature", "feeling hot", "feverish"],
    "cold": ["cold", "cough", "runny nose", "sneezing"],
    "chest_pain": ["chest pain", "tight chest", "heart pain"],
    "headache": ["headache", "migraine", "head pain"],
}

# Average wait time (minutes) per group; general is fallback
GROUP_WAIT_TIMES = {
    "fever": 15,
    "cold": 20,
    "chest_pain": 10,
    "headache": 25,
    "general": 30,
}

DEFAULT_WAIT = 30
MODEL_NAME = "all-MiniLM-L6-v2"
MIN_SIMILARITY = 0.3  # below this → return "general"

# Lazy-loaded model and cached phrase embeddings
_model = None
_phrase_embeddings: Optional[List[Tuple[str, str, List[float]]]] = None  # (phrase, group, embedding)


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _get_phrase_embeddings() -> List[Tuple[str, str, List[float]]]:
    """Precompute and cache embeddings for all example phrases. (phrase, group, embedding)."""
    global _phrase_embeddings
    if _phrase_embeddings is not None:
        return _phrase_embeddings
    model = _load_model()
    result = []
    for group, phrases in SYMPTOM_GROUPS.items():
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
    """Fallback: return first group whose phrase appears in text (case-insensitive)."""
    t = (text or "").strip().lower()
    if not t:
        return None
    for group, phrases in SYMPTOM_GROUPS.items():
        for phrase in phrases:
            if phrase.lower() in t:
                return group
    return None


def get_symptom_group(text: str) -> str:
    """
    Map free-text symptoms to a normalized group.
    Uses embedding similarity (sentence-transformers); falls back to keyword match on failure.
    Multi-symptom: split by " and ", match each part, return group with minimum wait time (urgent-friendly).
    """
    text = (text or "").strip()
    if not text:
        return "general"

    # Multi-symptom: split by " and " and choose group with minimum wait
    parts = [p.strip() for p in text.split(" and ") if p.strip()]
    if len(parts) <= 1:
        return _get_symptom_group_single(text)

    groups = []
    for part in parts:
        g = _get_symptom_group_single(part)
        groups.append(g)
    # Choose group with minimum wait time (urgent-friendly)
    best_group = min(groups, key=lambda g: GROUP_WAIT_TIMES.get(g, DEFAULT_WAIT))
    return best_group


def _get_symptom_group_single(text: str) -> str:
    """Single-text path: embedding match with keyword fallback."""
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
    # Fallback to keyword match
    kw = _keyword_match(text)
    return kw if kw else "general"


def get_wait_time(group: str) -> int:
    """Return group-based wait time in minutes; fallback DEFAULT_WAIT if group not found."""
    return GROUP_WAIT_TIMES.get(group, DEFAULT_WAIT)
