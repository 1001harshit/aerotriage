"""
Convert natural language into structured symptoms for triage.
Input: cleaned text (from Privacy Guard). Output: { symptoms: [], duration: null, severity_description: str }.
"""
import json
import re
from ai_core.llm_client import generate


def extract(clean_text: str) -> dict:
    """
    Returns dict: { "symptoms": ["chest pain", "dizziness"], "duration": null, "severity_description": "severe" }.
    """
    prompt = """You are a medical scribe. Extract structured symptom data from the patient's statement.
Return ONLY a JSON object, no other text. Use this exact shape:
{ "symptoms": ["symptom1", "symptom2"], "duration": null or "e.g. 2 hours", "severity_description": "mild" or "moderate" or "severe" }

Examples:
- "I have chest pain and dizziness" -> { "symptoms": ["chest pain", "dizziness"], "duration": null, "severity_description": "moderate" }
- "Severe abdominal pain for 3 hours" -> { "symptoms": ["severe abdominal pain"], "duration": "3 hours", "severity_description": "severe" }

Patient statement (PII already removed):
"""
    prompt += clean_text.strip() + "\n\nJSON:"

    result = generate(prompt)
    return _parse_extract_response(result.strip())


def _parse_extract_response(raw: str) -> dict:
    text = raw.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
    try:
        data = json.loads(text)
        symptoms = data.get("symptoms")
        if not isinstance(symptoms, list):
            symptoms = [str(s).strip() for s in (symptoms or "").split(",")] if symptoms else []
        symptoms = [str(s).strip().lower() for s in symptoms if s]
        duration = data.get("duration")
        if duration is not None:
            duration = str(duration).strip() or None
        severity_description = (data.get("severity_description") or "moderate").strip().lower()
        return {
            "symptoms": symptoms,
            "duration": duration,
            "severity_description": severity_description,
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "symptoms": [],
            "duration": None,
            "severity_description": "moderate",
        }
