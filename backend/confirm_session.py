"""
Confirmation session for triage/voice preview: store payload in Redis by token until user confirms.
TTL 15 minutes. Used by POST /triage and POST /voice-triage (preview) then POST /triage/confirm.
"""
import json
import os
import uuid
from typing import Any, Dict, Optional

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
KEY_PREFIX = "triage:confirm:"
TTL_SECONDS = 900  # 15 minutes


def _client():
    import redis
    return redis.from_url(REDIS_URL, decode_responses=True)


def create_session(payload: Dict[str, Any]) -> str:
    """Store payload in Redis; return confirmation_token. Caller must pass symptoms, severity, etc."""
    token = uuid.uuid4().hex
    key = KEY_PREFIX + token
    try:
        r = _client()
        r.set(key, json.dumps(payload), ex=TTL_SECONDS)
        return token
    except Exception:
        return ""


def get_session(token: str) -> Optional[Dict[str, Any]]:
    """Load session by token; return payload or None if missing/expired."""
    if not (token or "").strip():
        return None
    key = KEY_PREFIX + token.strip()
    try:
        r = _client()
        raw = r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return None


def delete_session(token: str) -> None:
    """Remove session after successful confirm."""
    if not (token or "").strip():
        return
    key = KEY_PREFIX + token.strip()
    try:
        r = _client()
        r.delete(key)
    except Exception:
        pass
