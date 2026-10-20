"""
Access control for staff-only routes and the Twilio webhook.

Both checks are switched on by environment variables so local development keeps
working with no setup:

- ADMIN_API_KEY: when set, the queue, stats, reasoning and reclassify routes
  (and the /ws/queue socket) require it in the X-Admin-Key header (or ?key= for
  the socket, since browsers cannot set headers on a WebSocket).
- TWILIO_AUTH_TOKEN: when set, /webhooks/whatsapp rejects requests whose
  X-Twilio-Signature does not match, so nobody but Twilio can inject messages.
  Set PUBLIC_WEBHOOK_URL too if the app runs behind a proxy or tunnel, because
  the signature covers the exact URL Twilio called.
"""
import base64
import hashlib
import hmac
import logging
import os
from typing import Mapping, Optional

from fastapi import Header, HTTPException, Request, WebSocket

logger = logging.getLogger(__name__)

if not os.getenv("ADMIN_API_KEY"):
    logger.warning("ADMIN_API_KEY is not set: staff routes are open to anyone who can reach the API")


def _admin_key_ok(presented: Optional[str]) -> bool:
    expected = os.getenv("ADMIN_API_KEY")
    if not expected:
        return True
    return presented is not None and hmac.compare_digest(presented, expected)


def require_admin(x_admin_key: Optional[str] = Header(None)) -> None:
    """FastAPI dependency for staff-only HTTP routes."""
    if not _admin_key_ok(x_admin_key):
        raise HTTPException(status_code=401, detail="Invalid or missing admin key")


def websocket_admin_ok(websocket: WebSocket) -> bool:
    return _admin_key_ok(websocket.query_params.get("key"))


def twilio_signature(auth_token: str, url: str, params: Mapping[str, str]) -> str:
    """Twilio's scheme: HMAC-SHA1 over the URL followed by each POST param name+value, sorted by name."""
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


async def verify_twilio_request(request: Request) -> None:
    """FastAPI dependency for the WhatsApp webhook."""
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not auth_token:
        return
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    url = os.getenv("PUBLIC_WEBHOOK_URL") or str(request.url)
    expected = twilio_signature(auth_token, url, params)
    presented = request.headers.get("X-Twilio-Signature", "")
    if not hmac.compare_digest(presented, expected):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
