"""
Queue API: GET /queue returns ordered triage queue.
Uses priority aging: priority = (6 - severity) + aging_factor * waiting_time_minutes.
When priorities tie, orders by arrival_time ascending (FIFO: oldest first = position 1).
"""
from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import APIRouter, HTTPException
from backend import database

AGING_FACTOR = 0.05
DISPLAY_WAIT_MIN_MINUTES = 10
# Round priority to this many decimals for sorting to reduce queue churn (less reordering)
PRIORITY_SORT_ROUND = 1
# Average minutes per patient for expected wait estimate
AVG_CONSULTATION_MINUTES = 5

router = APIRouter()


def _parse_iso(s: str) -> datetime:
    """Parse ISO format with optional Z."""
    if not s:
        return datetime.now(timezone.utc)
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.now(timezone.utc)


def _aged_priority(severity: int, arrival_time_str: str) -> float:
    """Compute priority with aging: (6 - severity) + aging_factor * waiting_time_minutes."""
    arrival = _parse_iso(arrival_time_str)
    now = datetime.now(timezone.utc)
    if arrival.tzinfo is None:
        arrival = arrival.replace(tzinfo=timezone.utc)
    wait_seconds = (now - arrival).total_seconds()
    waiting_minutes = max(0.0, wait_seconds / 60.0)
    return (6 - severity) + AGING_FACTOR * waiting_minutes


@router.get("/queue")
def get_queue():
    """
    Returns ordered queue (highest priority first).
    Priority is recomputed with aging. Ties broken by arrival_time (oldest first).
    Each entry: patient_id, priority (aged), position (1-based), severity, arrival_time.
    """
    rows = database.get_queue_from_sqlite()
    now = datetime.now(timezone.utc)

    entries = []
    for r in rows:
        pid = r.get("patient_id")
        severity = r.get("severity") or 2
        arrival_time = r.get("arrival_time") or ""
        priority_aged = _aged_priority(severity, arrival_time)
        entries.append({
            "patient_id": pid,
            "severity": severity,
            "arrival_time": arrival_time,
            "priority_aged": priority_aged,
            "mobile": r.get("mobile"),
            "name": r.get("name"),
            "reasoning": (r.get("reasoning") or "").strip() or None,
            "estimated_treatment_minutes": r.get("estimated_treatment_minutes"),
        })

    # Sort: highest priority first (rounded to reduce churn), then oldest first (FIFO) for ties
    entries.sort(key=lambda e: (-round(e["priority_aged"], PRIORITY_SORT_ROUND), e["arrival_time"] or ""))

    # Learned average treatment time by severity (from completed patients); fallback to fixed default
    learned_avg = database.get_avg_treatment_minutes_by_severity()

    result = []
    cumulative_wait = 0.0
    for position, e in enumerate(entries, start=1):
        # Use stored RAG/symptom estimate if present (matches what user was shown); else learned_avg by severity
        est_minutes = e.get("estimated_treatment_minutes")
        if est_minutes is None or est_minutes <= 0:
            est_minutes = learned_avg.get(e["severity"])
        if est_minutes is None or est_minutes <= 0:
            est_minutes = AVG_CONSULTATION_MINUTES
        # Expected wait = sum of estimated treatment times for all patients ahead in queue
        expected_wait_minutes = round(cumulative_wait, 1)
        cumulative_wait += est_minutes
        # Display wait is at least DISPLAY_WAIT_MIN_MINUTES so admin matches user-facing "minimum 10 min"
        display_wait_minutes = max(expected_wait_minutes, float(DISPLAY_WAIT_MIN_MINUTES))
        result.append({
            "patient_id": e["patient_id"],
            "priority": round(e["priority_aged"], 2),
            "position": position,
            "severity": e["severity"],
            "arrival_time": e["arrival_time"],
            "expected_wait_minutes": expected_wait_minutes,
            "expected_wait_display_minutes": round(display_wait_minutes, 1),
            "estimated_treatment_minutes": round(est_minutes, 1),
            "mobile": e.get("mobile"),
            "name": e.get("name"),
            "reasoning": e.get("reasoning"),
        })
    return result


@router.post("/queue/complete-first")
async def complete_first_patient():
    """
    Remove the first patient from the queue (mark as seen, remove from queue).
    Returns the completed patient. Broadcasts queue update to WebSocket clients.
    """
    entries = get_queue()
    if not entries:
        raise HTTPException(status_code=404, detail="Queue is empty")
    first = entries[0]
    patient_id = first["patient_id"]
    database.remove_from_queue(patient_id)
    database.mark_patient_completed(patient_id)
    try:
        from backend import redis_queue
        redis_queue.remove_from_queue(str(patient_id))
    except Exception:
        pass
    try:
        from backend.websocket_manager import ws_manager
        await ws_manager.broadcast_json({"type": "queue_update", "queue": get_queue()})
    except Exception:
        pass
    return {"completed": first, "message": "First patient removed from queue"}


def get_queue_entries():
    """Same logic as GET /queue; returns list of entries. Use for consistent position in POST /triage."""
    return get_queue()


def get_expected_wait_for_new_patient(
    severity: int,
    group_wait_minutes: Optional[float] = None,
) -> float:
    """
    Expected wait (minutes) if a new patient were added to the end of the queue.
    Uses same logic as get_queue(): stored estimated_treatment_minutes per patient so user and admin match.
    Returns cumulative wait (time until new patient would be seen); optional group_wait_minutes is added if provided (e.g. for "total time" display).
    """
    rows = database.get_queue_from_sqlite()
    entries = []
    for r in rows:
        pid = r.get("patient_id")
        sev = r.get("severity") or 2
        arrival_time = r.get("arrival_time") or ""
        priority_aged = _aged_priority(sev, arrival_time)
        entries.append({
            "patient_id": pid,
            "severity": sev,
            "arrival_time": arrival_time,
            "priority_aged": priority_aged,
            "estimated_treatment_minutes": r.get("estimated_treatment_minutes"),
        })
    entries.sort(
        key=lambda e: (-round(e["priority_aged"], PRIORITY_SORT_ROUND), e["arrival_time"] or "")
    )
    learned_avg = database.get_avg_treatment_minutes_by_severity()
    cumulative_wait = 0.0
    for e in entries:
        est = e.get("estimated_treatment_minutes")
        if est is None or est <= 0:
            est = learned_avg.get(e["severity"])
        if est is None or est <= 0:
            est = AVG_CONSULTATION_MINUTES
        cumulative_wait += est
    total = cumulative_wait + (group_wait_minutes or 0)
    return round(total, 1)


def get_display_wait(
    raw_minutes: float,
    min_minutes: int = 10,
) -> Tuple[float, str]:
    """
    Return (floored value, label) so displayed wait is at least min_minutes.
    Example: (15.0, "~15 min") or (10.0, "~10 min") when raw is 5.
    """
    display_minutes = max(raw_minutes, float(min_minutes))
    label = f"~{int(display_minutes)} min" if display_minutes >= 0 else "—"
    return (round(display_minutes, 1), label)
