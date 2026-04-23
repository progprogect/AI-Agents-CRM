"""Tests for agent config merge on PUT."""

import unittest

from app.api.v1.agents import _merge_agent_config


class TestMergeAgentConfig(unittest.TestCase):
    def test_escalation_deep_merge_preserves_other_keys(self) -> None:
        existing = {
            "agent_id": "a1",
            "escalation": {
                "enabled": True,
                "detect_contact": True,
                "custom_rules": [{"id": "r1", "name": "x", "description": "y"}],
            },
        }
        incoming = {"escalation": {"enabled": False}}
        out = _merge_agent_config(existing, incoming)
        self.assertEqual(out["escalation"]["enabled"], False)
        self.assertTrue(out["escalation"]["detect_contact"])
        self.assertEqual(len(out["escalation"]["custom_rules"]), 1)

    def test_shallow_merge_top_level(self) -> None:
        existing = {"project": "p", "escalation": {"enabled": True}}
        incoming = {"project": "p2"}
        out = _merge_agent_config(existing, incoming)
        self.assertEqual(out["project"], "p2")
        self.assertEqual(out["escalation"]["enabled"], True)

    def test_moderation_deep_merge_preserves_other_keys(self) -> None:
        existing = {
            "agent_id": "a1",
            "moderation": {
                "enabled": True,
                "provider": "openai",
                "categories": ["hate"],
            },
        }
        incoming = {"moderation": {"enabled": False}}
        out = _merge_agent_config(existing, incoming)
        self.assertEqual(out["moderation"]["enabled"], False)
        self.assertEqual(out["moderation"]["provider"], "openai")
        self.assertEqual(out["moderation"]["categories"], ["hate"])


if __name__ == "__main__":
    unittest.main()
