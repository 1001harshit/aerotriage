"""Admin API: reasoning transparency, reclassify, stats for dashboard."""
import json
from fastapi import APIRouter, HTTPException
from backend import database
from backend.queue_api import get_queue_entries

router = APIRouter()


@router.get("/patients/{patient_id}/reasoning")
def get_patient_reasoning(patient_id: int):
    """Return AI transparency: reasoning, RAG sources, voice transcript."""
    patient = database.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    rag = patient.get("rag_sources")
    if rag is None:
        rag_sources = []
    elif isinstance(rag, str):
        try:
            rag_sources = json.loads(rag) if rag.strip() else []
        except (TypeError, json.JSONDecodeError):
            rag_sources = []
    elif isinstance(rag, list):
        rag_sources = rag
    else:
        rag_sources = []
    return {
        "patient_id": patient_id,
        "reasoning": (patient.get("reasoning") or "").strip(),
        "rag_sources": rag_sources,
        "voice_transcript": patient.get("voice_transcript") or "",
        "severity": patient.get("severity"),
        "symptoms": patient.get("symptoms"),
    }


@router.post("/patients/{patient_id}/reclassify")
def reclassify_patient(patient_id: int, data: dict):
    """
    Re-run triage or set severity manually. Body: { "severity": 1-5 } to set directly,
    or { "symptoms": "..." } to re-run full triage (optional).
    """
    patient = database.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient.get("status") != "queued":
        raise HTTPException(status_code=400, detail="Patient not in queue")

    severity = data.get("severity")
    if severity is not None:
        if not (1 <= severity <= 5):
            raise HTTPException(status_code=400, detail="severity must be 1-5")
        database.update_patient_severity(patient_id, severity)
        database.refresh_queue_priority(patient_id, severity)
        try:
            from backend import redis_queue
            priority = (6 - severity) + 0.05 * 0
            redis_queue.add_to_queue(str(patient_id), priority)
        except Exception:
            pass
        entries = get_queue_entries()
        position = next((e["position"] for e in entries if e["patient_id"] == patient_id), None)
        return {"patient_id": patient_id, "severity": severity, "queue_position": position}
    # TODO: optional re-run full triage from symptoms
    raise HTTPException(status_code=400, detail="Provide severity (1-5) to reclassify")


@router.get("/stats")
def get_stats():
    """Analytics for dashboard: avg wait, critical handled, queue load."""
    from backend.database import get_avg_treatment_minutes_by_severity, get_stats as db_stats
    avg_by_sev = get_avg_treatment_minutes_by_severity()
    avg_wait = sum(avg_by_sev.values()) / len(avg_by_sev) if avg_by_sev else 0
    counts = db_stats()
    return {
        "average_wait_minutes": round(avg_wait, 1),
        "critical_cases_handled": counts["critical_cases_handled"],
        "queue_count": counts["queue_count"],
    }
