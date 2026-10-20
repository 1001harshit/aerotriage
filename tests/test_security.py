"""
Tests for staff-route and Twilio webhook protection.
Uses a tiny app wired with the same dependencies, so it runs without the ML stack.
"""
import os
import unittest
from unittest import mock

from fastapi import Depends, FastAPI, Form, WebSocket
from fastapi.testclient import TestClient

from backend.security import (
    require_admin,
    twilio_signature,
    verify_twilio_request,
    websocket_admin_ok,
)

app = FastAPI()


@app.get("/staff", dependencies=[Depends(require_admin)])
def staff():
    return {"ok": True}


@app.post("/hook", dependencies=[Depends(verify_twilio_request)])
def hook(Body: str = Form("")):
    return {"body": Body}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    if not websocket_admin_ok(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    await websocket.send_text("hi")
    await websocket.close()


client = TestClient(app)


class TestAdminKey(unittest.TestCase):
    def test_open_when_no_key_configured(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(client.get("/staff").status_code, 200)

    def test_rejects_missing_or_wrong_key(self):
        with mock.patch.dict(os.environ, {"ADMIN_API_KEY": "k1"}):
            self.assertEqual(client.get("/staff").status_code, 401)
            self.assertEqual(client.get("/staff", headers={"X-Admin-Key": "nope"}).status_code, 401)

    def test_accepts_right_key(self):
        with mock.patch.dict(os.environ, {"ADMIN_API_KEY": "k1"}):
            self.assertEqual(client.get("/staff", headers={"X-Admin-Key": "k1"}).status_code, 200)

    def test_websocket_needs_key_in_query(self):
        with mock.patch.dict(os.environ, {"ADMIN_API_KEY": "k1"}):
            with client.websocket_connect("/ws?key=k1") as conn:
                self.assertEqual(conn.receive_text(), "hi")
            with self.assertRaises(Exception):
                with client.websocket_connect("/ws") as conn:
                    conn.receive_text()


class TestTwilioSignature(unittest.TestCase):
    def test_matches_twilio_sdk(self):
        # Expected value computed with twilio.request_validator.RequestValidator.
        params = {
            "CallSid": "CA1234567890ABCDE",
            "Caller": "+12349013030",
            "Digits": "1234",
            "From": "+12349013030",
            "To": "+18005551212",
        }
        url = "https://example.com/myapp.php?foo=1&bar=2"
        self.assertEqual(
            twilio_signature("12345", url, params),
            "vNe7KK2kJwCsxc9K3OLkkKB3qqI=",
        )

    def test_webhook_rejects_unsigned_requests(self):
        with mock.patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "tok"}):
            self.assertEqual(client.post("/hook", data={"Body": "fever"}).status_code, 403)

    def test_webhook_accepts_signed_requests(self):
        with mock.patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "tok"}):
            sig = twilio_signature("tok", "http://testserver/hook", {"Body": "fever"})
            r = client.post("/hook", data={"Body": "fever"}, headers={"X-Twilio-Signature": sig})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json(), {"body": "fever"})

    def test_webhook_open_when_no_token_configured(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(client.post("/hook", data={"Body": "x"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
