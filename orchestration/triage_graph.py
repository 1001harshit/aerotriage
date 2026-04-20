from langgraph.graph import StateGraph
from langgraph.graph import END
from orchestration.agents.privacy_guard import remove_pii
from orchestration.agents.symptom_extractor import extract
from orchestration.agents.triage_agent import triage
from ai_core.triage_rules import apply_rules
from orchestration.agents.confidence_validator import validate
from orchestration.agents.scheduler_agent import schedule


class State(dict):
    """State: input, clean, extracted, rule_severity, rule_triggered, triage_result, validated_result, patient_id, queue_position."""
    pass


def privacy_node(state):
    clean = remove_pii(state["input"])
    return _pass_through(state, {"clean": clean})


def _pass_through(state, out):
    """Pass invocation-only keys so scheduler receives them on every path."""
    for key in ("preview_only", "mobile", "voice_transcript"):
        if key in state:
            out[key] = state[key]
    return out


def symptom_node(state):
    extracted = extract(state["clean"])
    return _pass_through(state, {"extracted": extracted})


def rule_node(state):
    symptoms_input = state.get("extracted") or {}
    symptoms_list = symptoms_input.get("symptoms") or []
    text = " ".join(symptoms_list) if symptoms_list else state.get("clean", "")
    severity, triggered = apply_rules(text)
    return _pass_through(state, {"rule_severity": severity, "rule_triggered": triggered})


def triage_node(state):
    extracted = state.get("extracted") or {}
    symptoms = extracted.get("symptoms") or []
    symptoms_text = " ".join(symptoms) if symptoms else state.get("clean", "")
    triage_result = triage(symptoms_text)
    return _pass_through(state, {"triage_result": triage_result})


def confidence_node(state):
    validated = validate(state["triage_result"])
    return _pass_through(state, {"validated_result": validated})


def scheduler_node(state):
    extracted = state.get("extracted") or {}
    symptoms_list = extracted.get("symptoms") or []
    symptoms_text = " ".join(symptoms_list) if symptoms_list else state.get("clean", "")

    if state.get("rule_triggered"):
        severity = state["rule_severity"]
        confidence = 1.0
        flag_for_review = False
        reasoning = f"Rule matched: severity {severity}."
        rag_sources = []
        symptom_group = ""
    else:
        v = state.get("validated_result") or {}
        tr = state.get("triage_result") or {}
        severity = v.get("severity", 2)
        confidence = v.get("confidence", 0.5)
        flag_for_review = v.get("flag_for_review", False)
        reasoning = tr.get("reasoning", "")
        rag_sources = tr.get("rag_sources", [])
        symptom_group = tr.get("symptom_group", "")

    # Preview-only: return severity/reasoning without creating patient or adding to queue.
    if state.get("preview_only"):
        return {
            "patient_id": None,
            "queue_position": 0,
            "severity": severity,
            "confidence": confidence,
            "flag_for_review": flag_for_review,
            "mobile": state.get("mobile"),
            "reasoning": reasoning,
            "rag_sources": rag_sources,
            "voice_transcript": state.get("voice_transcript"),
            "symptom_group": symptom_group,
        }

    result = schedule(
        symptoms=symptoms_text,
        severity=severity,
        confidence=confidence,
        flag_for_review=flag_for_review,
        mobile=state.get("mobile"),
    )
    return {
        "patient_id": result["patient_id"],
        "queue_position": result["queue_position"],
        "severity": severity,
        "confidence": confidence,
        "flag_for_review": flag_for_review,
        "mobile": state.get("mobile"),
        "reasoning": reasoning,
        "rag_sources": rag_sources,
        "voice_transcript": state.get("voice_transcript"),
    }


def route_after_rule(state):
    if state.get("rule_triggered"):
        return "scheduler"
    return "triage"


graph = StateGraph(State)

graph.add_node("privacy", privacy_node)
graph.add_node("symptom", symptom_node)
graph.add_node("rule", rule_node)
graph.add_node("triage", triage_node)
graph.add_node("confidence", confidence_node)
graph.add_node("scheduler", scheduler_node)

graph.set_entry_point("privacy")
graph.add_edge("privacy", "symptom")
graph.add_edge("symptom", "rule")
graph.add_conditional_edges("rule", route_after_rule, {"scheduler": "scheduler", "triage": "triage"})
graph.add_edge("triage", "confidence")
graph.add_edge("confidence", "scheduler")
graph.add_edge("scheduler", END)

triage_graph = graph.compile()
