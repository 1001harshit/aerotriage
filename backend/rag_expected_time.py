"""
RAG-based expected consultation time from triage_rag_dataset.json.
Finds the most similar case by symptom text and returns its doctor_time (minutes).
Uses sentence-transformers for consistency with symptom_grouping; fallback to symptom_grouping.
"""
from pathlib import Path
from typing import Optional, Tuple

# Lazy-loaded dataset and embeddings
_dataset: Optional[list] = None
_embeddings: Optional[list] = None
_model = None

DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "triage_rag_dataset.json"
MODEL_NAME = "all-MiniLM-L6-v2"
# Lower threshold so RAG matches more often and returns varied doctor_time from dataset (e.g. 12, 18, 20)
# instead of often falling back to symptom_grouping (e.g. GROUP_WAIT_TIMES["fever"]=15)
MIN_SIMILARITY = 0.20
DEFAULT_DOCTOR_TIME = 15  # only used if symptom_grouping fails


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _load_dataset() -> list:
    global _dataset
    if _dataset is not None:
        return _dataset
    if not DATASET_PATH.exists():
        _dataset = []
        return _dataset
    import json
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        _dataset = json.load(f)
    return _dataset


def _get_embeddings() -> Tuple[list, list]:
    """Return (dataset, list of embedding vectors)."""
    global _embeddings
    data = _load_dataset()
    if not data:
        return data, []
    if _embeddings is not None and len(_embeddings) == len(data):
        return data, _embeddings
    model = _load_model()
    texts = [item.get("symptoms") or "" for item in data]
    _embeddings = model.encode(texts, convert_to_numpy=True).tolist()
    return data, _embeddings


def _cosine_similarity(a: list, b: list) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def get_expected_time_from_rag(symptoms_text: str) -> Tuple[float, str]:
    """
    Return (doctor_time_minutes, normalized_group) from RAG dataset.
    Uses embedding similarity over triage_rag_dataset.json.
    Fallback: uses symptom_grouping.get_wait_time if dataset missing or no good match.
    """
    text = (symptoms_text or "").strip()
    if not text:
        from backend.symptom_grouping import get_symptom_group, get_wait_time
        group = get_symptom_group(text) or "general"
        return float(get_wait_time(group)), group

    data, embeddings = _get_embeddings()
    if not data or not embeddings:
        from backend.symptom_grouping import get_symptom_group, get_wait_time
        group = get_symptom_group(text)
        return float(get_wait_time(group)), group or "general"

    try:
        model = _load_model()
        query_emb = model.encode([text], convert_to_numpy=True)[0].tolist()
        best_idx = -1
        best_sim = MIN_SIMILARITY
        for i, emb in enumerate(embeddings):
            sim = _cosine_similarity(query_emb, emb)
            if sim > best_sim:
                best_sim = sim
                best_idx = i
        if best_idx >= 0:
            item = data[best_idx]
            doctor_time = item.get("doctor_time")
            if doctor_time is not None and doctor_time > 0:
                group = (item.get("normalized_group") or "general").replace(" ", "_")
                return float(doctor_time), group
    except Exception:
        pass

    # Fallback: no RAG match → symptom_grouping (e.g. fever=15, cold=20, headache=25 in GROUP_WAIT_TIMES)
    from backend.symptom_grouping import get_symptom_group, get_wait_time
    group = get_symptom_group(text)
    wait = get_wait_time(group) if group else DEFAULT_DOCTOR_TIME
    return float(wait), group or "general"
