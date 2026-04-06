"""Tests for vet_informational medical_question_policy expansion."""

import unittest

from app.chains.escalation_chain import (
    MEDICAL_QUESTION_POLICY_VET_INFORMATIONAL,
    expand_medical_question_policy_for_prompt,
    _expand_policies_dict,
)


class TestEscalationVetPolicy(unittest.TestCase):
    def test_expands_vet_informational_token(self) -> None:
        out = expand_medical_question_policy_for_prompt(MEDICAL_QUESTION_POLICY_VET_INFORMATIONAL)
        self.assertIn("Do NOT escalate", out)
        self.assertNotIn("vet_informational", out)
        self.assertIn("не эскалировать", out)

    def test_passes_through_other_policies(self) -> None:
        self.assertEqual(
            expand_medical_question_policy_for_prompt("handoff_or_book"),
            "handoff_or_book",
        )

    def test_expand_policies_dict_medical_key(self) -> None:
        d = _expand_policies_dict(
            {
                "medical_question": MEDICAL_QUESTION_POLICY_VET_INFORMATIONAL,
                "urgent_case": "advise_emergency_and_handoff",
            }
        )
        self.assertIn("Do NOT escalate", d["medical_question"])
        self.assertEqual(d["urgent_case"], "advise_emergency_and_handoff")


if __name__ == "__main__":
    unittest.main()
