"""
Redis sorted set for real-time triage queue.
Requires: Redis running locally (offline-first). Key: triage_queue, score = priority, value = patient_id.
"""
import os
from typing import List, Optional

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
TRIAGE_QUEUE_KEY = "triage_queue"


def _client():
    import redis
    return redis.from_url(REDIS_URL, decode_responses=True)


def add_to_queue(patient_id: str, priority: float) -> None:
    """ZADD triage_queue with score = priority, value = patient_id."""
    r = _client()
    r.zadd(TRIAGE_QUEUE_KEY, {patient_id: priority})


def remove_from_queue(patient_id: str) -> None:
    """Remove patient_id from triage_queue ZSET."""
    r = _client()
    r.zrem(TRIAGE_QUEUE_KEY, patient_id)


def get_queue_order() -> List[str]:
    """Return ordered list of patient_ids (highest priority first). ZRANGE by score desc."""
    r = _client()
    # Redis ZRANGE with rev=True gives highest score first
    return r.zrange(TRIAGE_QUEUE_KEY, 0, -1, desc=True)


def get_queue_position(patient_id: str) -> Optional[int]:
    """0-based position in queue (0 = first). Returns None if not in set."""
    r = _client()
    rank = r.zrevrank(TRIAGE_QUEUE_KEY, patient_id)
    return int(rank) if rank is not None else None


def get_queue_with_scores() -> List[tuple]:
    """Return list of (patient_id, score) ordered by priority desc."""
    r = _client()
    return r.zrevrange(TRIAGE_QUEUE_KEY, 0, -1, withscores=True)
