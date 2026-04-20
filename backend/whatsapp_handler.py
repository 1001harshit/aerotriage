"""
WhatsApp webhook message handler: state machine and reply formatting.
- AI handles all chat: first message can be greeting; bot asks for symptoms until user sends symptoms.
- Expected wait from RAG (triage_rag_dataset.json); add to queue only after user confirms YES.
- Confirmation: Yes/No; only on Yes → ask name → ask phone → add to queue.
"""
import asyncio
import json
from typing import Optional

from backend import database as db
from backend.queue_api import (
    get_queue_entries,
    get_expected_wait_for_new_patient,
    get_display_wait,
)
from backend.hybrid_severity import get_symptom_group, get_base_severity, CONSULTATION_TIME_MINUTES
from backend.rag_expected_time import get_expected_time_from_rag
from backend.whatsapp_state import get_state, set_state, clear_state
from orchestration.agents.scheduler_agent import schedule

# Greetings/short phrases that are not symptoms — bot responds and asks for symptoms
GREETINGS = frozenset({
    "hi", "hello", "hey", "helo", "hii", "hiii",
    "good morning", "good afternoon", "good evening", "gm", "gn",
    "help", "start", "hi there", "hello there",
    "yes", "no", "ok", "okay", "thanks", "thank you",
})
# Minimal symptom hints: if message contains one of these we treat as symptoms
SYMPTOM_HINTS = (
    "pain", "fever", "headache", "cough", "cold", "chest", "stomach", "belly",
    "dizzy", "vomit", "nausea", "breath", "bleed", "injury", "cut", "burn",
    "rash", "weak", "tired", "sore", "throat", "nose", "congestion",
)


def _is_likely_symptoms(text: str) -> bool:
    """True if message looks like symptom description rather than greeting/off-topic."""
    t = (text or "").strip().lower()
    if not t:
        return False
    if t in GREETINGS:
        return False
    if len(t) < 12 and not any(h in t for h in SYMPTOM_HINTS):
        return False
    return True


# Severity bands for user-facing message (1-2 Low, 3 Medium, 4-5 High/Urgent)
def _severity_band(severity: int) -> str:
    if severity >= 4:
        return "High / Urgent"
    if severity == 3:
        return "Medium"
    return "Low"


def _ask_for_symptoms() -> str:
    """Friendly prompt when user hasn’t given symptoms yet."""
    return (
        "Hi! I'm here to help. Please describe your symptoms in a short message "
        "(e.g. fever, headache, chest pain)."
    )


def format_triage_reply(
    severity: int,
    condition_label: str,
    expected_wait_display_minutes: float,
    wait_label: str,
) -> str:
    """Build triage reply with expected wait (RAG) and Yes/No confirmation."""
    band = _severity_band(severity)
    return (
        f"AeroTriage Result\n\n"
        f"Condition: {condition_label}\n"
        f"Severity: {band} ({severity}/5)\n\n"
        f"Expected wait time: {wait_label} (minimum 10 min)\n\n"
        f"Reply YES to confirm appointment or NO to cancel."
    )


def _is_confirm_yes(text: str) -> bool:
    """True if user confirmed (Yes button or typed YES)."""
    t = (text or "").strip().upper()
    return t in ("YES", "Y", "1")

def _is_confirm_no(text: str) -> bool:
    """True if user declined (No button or typed NO)."""
    t = (text or "").strip().upper()
    return t in ("NO", "N", "0")


def _looks_like_phone(text: str) -> bool:
    """True if text looks like a phone number (enough digits, not a word like yes/no)."""
    if not text or len(text) > 25:
        return False
    digits = sum(1 for c in text if c.isdigit())
    # At least 6 digits and no common confirmation words
    if digits < 6:
        return False
    t = text.strip().upper()
    if t in ("YES", "Y", "NO", "N", "OK", "SAME", "CONFIRM"):
        return False
    return True


# Twilio stops waiting for the webhook after ~15s. We must respond before that or the reply never reaches WhatsApp.
TRIAGE_TIMEOUT_SECONDS = 8

async def handle_whatsapp_message(body: str, from_number: str) -> str:
    """
    State machine: no state → if greeting/short then ask for symptoms; else triage + awaiting_confirm.
    On YES → awaiting_name → awaiting_phone → schedule. On NO → clear and ask for symptoms later.
    Triage is run with a timeout so we always respond within Twilio's limit.
    Returns the reply text to send back (no TwiML).
    """
    from orchestration.triage_graph import triage_graph

    body_stripped = (body or "").strip()
    state = get_state(from_number)

    # No conversation state: handle chat — only run triage when message looks like symptoms
    if not state:
        if not body_stripped:
            return _ask_for_symptoms()
        if not _is_likely_symptoms(body_stripped):
            return _ask_for_symptoms()
        try:
            group = get_symptom_group(body_stripped)
        except Exception:
            group = "general"
        severity = 3
        reasoning = ""
        rag_sources = []
        try:
            rag_doctor_min, _ = get_expected_time_from_rag(body_stripped)
        except Exception:
            rag_doctor_min = float(CONSULTATION_TIME_MINUTES.get(group, 20))
        try:
            state_input = {"input": body_stripped, "preview_only": True}
            result = await asyncio.wait_for(
                asyncio.to_thread(triage_graph.invoke, state_input),
                timeout=TRIAGE_TIMEOUT_SECONDS,
            )
            severity = result.get("severity", 2)
            reasoning = result.get("reasoning") or ""
            rag_sources = result.get("rag_sources") or []
            try:
                rag_doctor_min, _ = get_expected_time_from_rag(body_stripped)
            except Exception:
                rag_doctor_min = float(CONSULTATION_TIME_MINUTES.get(group, 20))
        except asyncio.TimeoutError:
            pass  # use fallback severity 3 and rag_doctor_min already set
        except Exception:
            pass
        # Show "time until you're seen" only (cumulative), so it matches admin and reduces when patients are completed
        virtual_wait = get_expected_wait_for_new_patient(severity, group_wait_minutes=0)
        display_minutes, wait_label = get_display_wait(virtual_wait, min_minutes=10)
        condition_label = group.replace("_", " ").title()
        set_state(
            from_number,
            {
                "stage": "awaiting_confirm",
                "symptoms": body_stripped,
                "severity": severity,
                "reasoning": reasoning,
                "rag_sources": rag_sources,
                "symptom_group": group,
                "group_wait_minutes": rag_doctor_min,
                "expected_wait_label": wait_label,
                "expected_wait_display_minutes": display_minutes,
            },
        )
        return format_triage_reply(severity, condition_label, display_minutes, wait_label)

    stage = state.get("stage")

    if stage == "awaiting_confirm":
        if _is_confirm_yes(body_stripped):
            set_state(
                from_number,
                {
                    **state,
                    "stage": "awaiting_name",
                },
            )
            return "Please enter your name."
        if _is_confirm_no(body_stripped):
            clear_state(from_number)
            return "Booking cancelled. Send your symptoms when you're ready to try again."
        # User sent more symptoms: combine with previous and re-run triage → return updated score
        if body_stripped:
            combined_symptoms = ((state.get("symptoms") or "").strip() + " " + body_stripped).strip()
            if not combined_symptoms:
                combined_symptoms = body_stripped
            try:
                group = get_symptom_group(combined_symptoms)
            except Exception:
                group = "general"
            severity = 3
            reasoning = ""
            rag_sources = []
            try:
                rag_doctor_min, _ = get_expected_time_from_rag(combined_symptoms)
            except Exception:
                rag_doctor_min = float(CONSULTATION_TIME_MINUTES.get(group, 20))
            try:
                state_input = {"input": combined_symptoms, "preview_only": True}
                result = await asyncio.wait_for(
                    asyncio.to_thread(triage_graph.invoke, state_input),
                    timeout=TRIAGE_TIMEOUT_SECONDS,
                )
                severity = result.get("severity", 2)
                reasoning = result.get("reasoning") or ""
                rag_sources = result.get("rag_sources") or []
                try:
                    rag_doctor_min, _ = get_expected_time_from_rag(combined_symptoms)
                except Exception:
                    rag_doctor_min = float(CONSULTATION_TIME_MINUTES.get(group, 20))
            except asyncio.TimeoutError:
                pass
            except Exception:
                pass
            # Same as above: time until seen (cumulative only), matches admin
            virtual_wait = get_expected_wait_for_new_patient(severity, group_wait_minutes=0)
            display_minutes, wait_label = get_display_wait(virtual_wait, min_minutes=10)
            condition_label = group.replace("_", " ").title()
            set_state(
                from_number,
                {
                    "stage": "awaiting_confirm",
                    "symptoms": combined_symptoms,
                    "severity": severity,
                    "reasoning": reasoning,
                    "rag_sources": rag_sources,
                    "symptom_group": group,
                    "group_wait_minutes": rag_doctor_min,
                    "expected_wait_label": wait_label,
                    "expected_wait_display_minutes": display_minutes,
                },
            )
            return format_triage_reply(severity, condition_label, display_minutes, wait_label)
        return "Please reply YES to confirm or NO to cancel."

    if stage == "awaiting_name":
        name = body_stripped or "—"
        set_state(from_number, {**state, "stage": "awaiting_phone", "name": name})
        return "Please confirm your phone number or type a new one."

    if stage == "awaiting_phone":
        # Save all needed data from state, then clear immediately to prevent duplicate appointment on double-submit.
        saved_symptoms = state.get("symptoms") or ""
        saved_severity = state.get("severity", 2)
        saved_reasoning = (state.get("reasoning") or "").strip()
        raw_rag = state.get("rag_sources")
        if isinstance(raw_rag, list):
            saved_rag_sources = raw_rag
        elif isinstance(raw_rag, str):
            try:
                saved_rag_sources = json.loads(raw_rag) if raw_rag.strip() else []
            except (TypeError, json.JSONDecodeError):
                saved_rag_sources = []
        else:
            saved_rag_sources = []
        saved_name = state.get("name") or "—"
        # If user replied "yes" or similar to "confirm phone", use WhatsApp number; else use their typed number or WhatsApp
        if not body_stripped:
            saved_mobile = from_number
        elif _is_confirm_yes(body_stripped) or body_stripped.upper() in ("OK", "SAME", "USE THIS", "MY NUMBER", "CONFIRM"):
            saved_mobile = from_number
        elif _looks_like_phone(body_stripped):
            saved_mobile = body_stripped
        else:
            saved_mobile = from_number
        # Use the same expected wait we showed at preview (stored in state), so confirm message matches user and admin
        shown_wait_label = state.get("expected_wait_label")
        if not shown_wait_label:
            _, shown_wait_label = get_display_wait(state.get("expected_wait_display_minutes") or 0, min_minutes=10)
        saved_estimated_minutes = state.get("group_wait_minutes")

        clear_state(from_number)

        result = schedule(
            symptoms=saved_symptoms,
            severity=saved_severity,
            confidence=0.9,
            flag_for_review=False,
            mobile=saved_mobile,
            name=saved_name,
            estimated_treatment_minutes=saved_estimated_minutes,
        )
        patient_id = result["patient_id"]
        db.update_patient_reasoning(
            patient_id,
            reasoning=saved_reasoning,
            rag_sources=json.dumps(saved_rag_sources),
            voice_transcript=None,
        )
        entries = get_queue_entries()
        try:
            from backend.websocket_manager import ws_manager
            await ws_manager.broadcast_json({"type": "queue_update", "queue": entries})
        except Exception:
            pass
        return f"Appointment confirmed.\nExpected wait: {shown_wait_label}"

    # Unknown stage: clear and ask for symptoms
    clear_state(from_number)
    return "Please send your symptoms in a short message (e.g. chest pain, fever)."
