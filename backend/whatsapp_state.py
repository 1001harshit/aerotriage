"""
WhatsApp conversation state for multi-step booking flow.
Stored in Redis: key whatsapp:conv:{from_number}, value JSON, TTL 1 hour.
"""
import json
import os
from typing import Any, Dict, Optional

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
KEY_PREFIX = "whatsapp:conv:"
TTL_SECONDS = 3600


def _client():
    import redis
    return redis.from_url(REDIS_URL, decode_responses=True)


def get_state(from_number: str) -> Optional[Dict[str, Any]]:
    """Get conversation state for this sender. Returns None if missing or expired."""
    key = KEY_PREFIX + (from_number or "").strip()
    if not key or key == KEY_PREFIX:
        return None
    try:
        r = _client()
        raw = r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return None


def set_state(from_number: str, payload: Dict[str, Any]) -> None:
    """Set conversation state and refresh TTL."""
    key = KEY_PREFIX + (from_number or "").strip()
    if not key or key == KEY_PREFIX:
        return
    try:
        r = _client()
        r.set(key, json.dumps(payload), ex=TTL_SECONDS)
    except Exception:
        pass


def clear_state(from_number: str) -> None:
    """Remove conversation state for this sender."""
    key = KEY_PREFIX + (from_number or "").strip()
    if not key or key == KEY_PREFIX:
        return
    try:
        r = _client()
        r.delete(key)
    except Exception:
        pass
