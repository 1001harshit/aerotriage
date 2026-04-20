import asyncio
import json
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from orchestration.triage_graph import triage_graph

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.queue_api import (
    router as queue_router,
    get_queue_entries,
    get_expected_wait_for_new_patient,
    get_display_wait,
)
from backend.admin_api import router as admin_router
from backend.websocket_manager import ws_manager
from backend.symptom_grouping import get_symptom_group
from backend.rag_expected_time import get_expected_time_from_rag
from backend.confirm_session import create_session, get_session, delete_session

app.include_router(queue_router)
app.include_router(admin_router)
from backend import database as db


def _triage_response(result):
    # Use same ordering as GET /queue (aged priority + FIFO) for queue_position
    entries = get_queue_entries()
    pid = result["patient_id"]
    position = next((e["position"] for e in entries if e["patient_id"] == pid), result.get("queue_position", 1))
    out = {
        "patient_id": pid,
        "severity": result["severity"],
        "confidence": result.get("confidence"),
        "queue_position": position,
        "flag_for_review": result.get("flag_for_review", False),
    }
    if result.get("mobile") is not None:
        out["mobile"] = result["mobile"]
    return out


@app.post("/triage")
async def triage_patient(data: dict):
    """
    Preview-only: run triage and symptom grouping, return severity + expected wait + confirmation_token.
    Patient is NOT added to queue until POST /triage/confirm with token + name + phone.
    """
    symptoms_text = (data.get("symptoms") or "").strip()
    if not symptoms_text:
        raise HTTPException(status_code=400, detail="symptoms required")
    state_input = {"input": symptoms_text, "preview_only": True}
    if data.get("mobile"):
        state_input["mobile"] = data.get("mobile")
    result = await asyncio.to_thread(triage_graph.invoke, state_input)
    severity = result.get("severity", 2)
    reasoning = result.get("reasoning") or ""
    rag_sources = result.get("rag_sources") or []
    group = result.get("symptom_group") or get_symptom_group(symptoms_text)
    rag_doctor_min, _ = get_expected_time_from_rag(symptoms_text)
    # Show "time until seen" only (cumulative), so it matches admin and reduces when patients are completed
    virtual_wait = get_expected_wait_for_new_patient(severity, group_wait_minutes=0)
    display_minutes, wait_label = get_display_wait(virtual_wait, min_minutes=10)

    payload = {
        "symptoms": symptoms_text,
        "severity": severity,
        "reasoning": reasoning,
        "rag_sources": rag_sources,
        "symptom_group": group,
        "group_wait_minutes": rag_doctor_min,
        "voice_transcript": None,
    }
    confirmation_token = create_session(payload)
    if not confirmation_token:
        raise HTTPException(status_code=503, detail="Session storage unavailable")

    condition_label = group.replace("_", " ").title()
    return {
        "severity": severity,
        "symptom_group": group,
        "condition": condition_label,
        "expected_wait_minutes": display_minutes,
        "expected_wait_label": wait_label,
        "message": f"Condition: {condition_label}. Severity: {severity}/5. Estimated wait: {wait_label} (minimum 10 min). Use POST /triage/confirm with this token to book.",
        "confirmation_token": confirmation_token,
    }


@app.post("/triage/confirm")
async def triage_confirm(data: dict):
    """
    Confirm appointment: pass confirmation_token + name + phone from preview step.
    Creates patient and adds to queue; returns patient_id, queue_position, expected_wait.
    """
    token = (data.get("confirmation_token") or "").strip()
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or data.get("mobile") or "").strip() or name
    if not token:
        raise HTTPException(status_code=400, detail="confirmation_token required")
    session = get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Confirmation session expired or invalid")
    symptoms = session.get("symptoms") or ""
    severity = session.get("severity", 2)
    reasoning = session.get("reasoning") or ""
    rag_sources = session.get("rag_sources") or []
    session_name = (session.get("name") or "").strip()
    confirm_name = (data.get("name") or "").strip() or session_name

    delete_session(token)

    from orchestration.agents.scheduler_agent import schedule
    result = schedule(
        symptoms=symptoms,
        severity=severity,
        confidence=0.9,
        flag_for_review=False,
        mobile=phone,
        name=confirm_name,
        estimated_treatment_minutes=session.get("group_wait_minutes"),
    )
    patient_id = result["patient_id"]
    db.update_patient_reasoning(
        patient_id,
        reasoning=reasoning,
        rag_sources=json.dumps(rag_sources),
        voice_transcript=session.get("voice_transcript"),
    )

    entries = get_queue_entries()
    expected_wait_minutes = 0
    for e in entries:
        if e.get("patient_id") == patient_id:
            expected_wait_minutes = e.get("expected_wait_minutes", 0)
            break
    display_minutes, wait_label = get_display_wait(expected_wait_minutes, min_minutes=10)
    try:
        await ws_manager.broadcast_json({"type": "queue_update", "queue": entries})
    except Exception:
        pass
    return {
        "patient_id": patient_id,
        "queue_position": result.get("queue_position", 0),
        "severity": severity,
        "expected_wait_minutes": display_minutes,
        "expected_wait_label": wait_label,
    }


# WhatsApp webhook: use your direct webhook URL. Reply is returned in TwiML (no Twilio REST API / SID / auth).
@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    Body: str = Form(None, alias="Body"),
    ButtonText: str = Form(None, alias="ButtonText"),
    From: str = Form(..., alias="From"),
):
    """
    WhatsApp webhook. Reply is sent by returning TwiML in this response (direct link / webhook URL only).
    """
    import logging
    import time
    body = (Body or ButtonText or "").strip()
    from_number = (From or "").strip()
    from_last = from_number[-4:] if len(from_number) >= 4 else "****"
    msg_type = "empty" if not body else ("yes" if body.upper() == "YES" else "symptoms" if len(body) > 3 else "short")
    logging.getLogger(__name__).info("whatsapp from=***%s len=%s type=%s", from_last, len(body), msg_type)
    t0 = time.perf_counter()
    try:
        from backend.whatsapp_handler import handle_whatsapp_message
        reply_text = await handle_whatsapp_message(body, from_number)
        elapsed = time.perf_counter() - t0
        logging.getLogger(__name__).info("whatsapp reply ready in %.1fs (Twilio needs <15s)", elapsed)
        return _twiml_reply(reply_text)
    except Exception:
        logging.getLogger(__name__).exception("whatsapp webhook error")
        return _twiml_reply("We are unable to process your request right now. Please try again later.")


def _twiml_reply(text: str):
    from fastapi.responses import Response
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{_escape_xml(text)}</Message></Response>'
    return Response(content=xml, media_type="application/xml")


def _escape_xml(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;"))


@app.websocket("/ws/queue")
async def websocket_queue(websocket: WebSocket):
    """Live queue updates for admin dashboard. Sends { type: 'queue_update', queue: [...] } on connect and on every triage/complete-first."""
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json({"type": "queue_update", "queue": get_queue_entries()})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.post("/voice-triage")
async def voice_triage(audio: UploadFile = File(...)):
    """
    Preview-only: transcribe audio, run triage + symptom grouping, return result + confirmation_token.
    Patient is NOT added to queue until POST /triage/confirm with token + name + phone.
    """
    from voice.whisper_processor import transcribe
    contents = await audio.read()
    text = transcribe(contents)
    if not text:
        return {"error": "No speech detected in audio"}
    result = await asyncio.to_thread(
        triage_graph.invoke,
        {"input": text, "voice_transcript": text, "preview_only": True},
    )
    severity = result.get("severity", 2)
    reasoning = result.get("reasoning") or ""
    rag_sources = result.get("rag_sources") or []

    group = get_symptom_group(text)
    group_wait = get_wait_time(group)
    virtual_wait = get_expected_wait_for_new_patient(severity, group_wait_minutes=0)
    display_minutes, wait_label = get_display_wait(virtual_wait, min_minutes=10)

    payload = {
        "symptoms": text,
        "severity": severity,
        "reasoning": reasoning,
        "rag_sources": rag_sources,
        "symptom_group": group,
        "group_wait_minutes": group_wait,
        "voice_transcript": text,
    }
    confirmation_token = create_session(payload)
    if not confirmation_token:
        raise HTTPException(status_code=503, detail="Session storage unavailable")

    condition_label = group.replace("_", " ").title()
    return {
        "transcript": text,
        "severity": severity,
        "symptom_group": group,
        "condition": condition_label,
        "expected_wait_minutes": display_minutes,
        "expected_wait_label": wait_label,
        "message": f"Condition: {condition_label}. Severity: {severity}/5. Estimated wait: {wait_label}. Use POST /triage/confirm with this token to book.",
        "confirmation_token": confirmation_token,
    }

