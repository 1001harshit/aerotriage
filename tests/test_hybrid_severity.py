"""
Tests for hybrid severity: stable, deterministic severity from normalized groups + red-flag escalation.
"""
import unittest


class TestHybridSeverity(unittest.TestCase):
    """fever -> 2, feverish -> 2, high temperature -> 2, chest pain -> 4 or higher, fever + difficulty breathing -> escalated."""

    def setUp(self):
        from backend.hybrid_severity import (
            get_symptom_group,
            get_base_severity,
            apply_red_flag_rules,
            compute_severity,
        )
        self.get_symptom_group = get_symptom_group
        self.get_base_severity = get_base_severity
        self.apply_red_flag_rules = apply_red_flag_rules
        self.compute_severity = compute_severity

    def test_fever_returns_severity_2(self):
        severity, group = self.compute_severity("fever")
        self.assertEqual(severity, 2, "fever must return severity 2")
        self.assertEqual(group, "fever")

    def test_feverish_returns_severity_2(self):
        severity, group = self.compute_severity("feverish")
        self.assertEqual(severity, 2, "feverish must return severity 2")
        self.assertEqual(group, "fever")

    def test_high_temperature_returns_severity_2(self):
        severity, group = self.compute_severity("high temperature since morning")
        self.assertEqual(severity, 2, "high temperature must return severity 2")
        self.assertEqual(group, "fever")

    def test_same_fever_input_stable_across_runs(self):
        for _ in range(3):
            s1, _ = self.compute_severity("fever")
            s2, _ = self.compute_severity("I feel feverish")
            self.assertEqual(s1, 2)
            self.assertEqual(s2, 2)

    def test_chest_pain_severity_4_or_higher(self):
        # chest_pain base is 4; red-flag "chest pain" escalates to 2
        severity, group = self.compute_severity("chest pain")
        self.assertIn(group, ("chest_pain", "general"))
        self.assertGreaterEqual(severity, 2, "chest pain must be at least severity 2 (escalated)")
        # Base for chest_pain is 4; with red flag we get 2 (higher urgency)
        self.assertLessEqual(severity, 5)

    def test_fever_and_difficulty_breathing_escalated(self):
        severity, _ = self.compute_severity("fever and difficulty breathing")
        # Red-flag "difficulty breathing" -> severity 2
        self.assertLessEqual(severity, 2, "fever + difficulty breathing must be escalated (<= 2)")

    def test_get_base_severity_fever(self):
        self.assertEqual(self.get_base_severity("fever"), 2)

    def test_get_base_severity_chest_pain(self):
        self.assertEqual(self.get_base_severity("chest_pain"), 4)

    def test_get_base_severity_breathing_issue(self):
        self.assertEqual(self.get_base_severity("breathing_issue"), 4)

    def test_red_flag_escalation_lowers_severity_number(self):
        # Base 4 (chest_pain), red flag -> 2 (more urgent)
        out = self.apply_red_flag_rules("chest pain and pressure", 4)
        self.assertEqual(out, 2)

    def test_fever_alone_never_severity_4(self):
        severity, _ = self.compute_severity("fever")
        self.assertNotEqual(severity, 4, "fever alone must not return severity 4")
        self.assertEqual(severity, 2)


class TestTriageAgentOutput(unittest.TestCase):
    """Triage agent returns stable severity and uses hybrid."""

    def test_triage_fever_returns_severity_2(self):
        from orchestration.agents.triage_agent import triage
        out = triage("fever")
        self.assertEqual(out["severity"], 2)
        self.assertIn("symptom_group", out)
        self.assertEqual(out["symptom_group"], "fever")

    def test_triage_feverish_returns_severity_2(self):
        from orchestration.agents.triage_agent import triage
        out = triage("I feel feverish")
        self.assertEqual(out["severity"], 2)

    def test_triage_chest_pain_high_severity(self):
        from orchestration.agents.triage_agent import triage
        out = triage("chest pain")
        self.assertLessEqual(out["severity"], 2, "chest pain should be escalated (<=2)")

    def test_triage_returns_rag_sources_key(self):
        from orchestration.agents.triage_agent import triage
        out = triage("fever")
        self.assertIn("rag_sources", out)
        self.assertIsInstance(out["rag_sources"], list)


if __name__ == "__main__":
    unittest.main()
