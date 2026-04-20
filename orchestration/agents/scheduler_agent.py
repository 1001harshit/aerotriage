"""
Adds patient to queue: Redis ZSET (real-time) and SQLite (permanent).
Priority = (6 - severity) + aging_factor * waiting_time_minutes. waiting_time = 0 at insert.
Returns patient_id, queue_position, severity, confidence for API response.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

# Backend storage (avoid circular import by importing inside functions if needed)

AGING_FACTOR = 0.05


def schedule(
    symptoms: Union[str, List[str]],
    severity: int,
    confidence: Optional[float] = None,
    arrival_time: Optional[str] = None,
    flag_for_review: bool = False,
    mobile: Optional[str] = None,
    name: Optional[str] = None,
    estimated_treatment_minutes: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Insert patient into SQLite and Redis queue. Return patient_id, queue_position, severity, confidence.
    estimated_treatment_minutes: RAG/symptom-based estimate (so admin queue expected wait matches user).
    """
    from backend import database
    from backend import redis_queue

    if isinstance(symptoms, list):
        symptoms_text = ", ".join(symptoms)
    else:
        symptoms_text = str(symptoms)

    arrival_time = arrival_time or datetime.utcnow().isoformat() + "Z"
    waiting_minutes = 0.0
    priority = (6 - severity) + AGING_FACTOR * waiting_minutes

    patient_id = database.insert_patient(
        symptoms=symptoms_text,
        severity=severity,
        confidence=confidence,
        arrival_time=arrival_time,
        flag_for_review=flag_for_review,
        mobile=mobile,
        name=name,
        estimated_treatment_minutes=estimated_treatment_minutes,
    )
    database.insert_queue_entry(patient_id=patient_id, priority=priority)
    redis_queue.add_to_queue(str(patient_id), priority)

    queue_position = redis_queue.get_queue_position(str(patient_id))
    if queue_position is None:
        queue_position = 0

    return {
        "patient_id": patient_id,
        "queue_position": queue_position + 1,  # 1-based for API
        "severity": severity,
        "confidence": confidence,
    }
