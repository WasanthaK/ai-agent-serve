import unittest

from agent_skills.base import AgentSkill
from agent_skills.registry import SkillRegistry
import skill_promotion as promotion


class SkillPromotionTests(unittest.TestCase):
    def test_next_minor_version_is_deterministic(self):
        self.assertEqual(
            promotion._next_minor_version("1.0.0"),
            "1.1.0",
        )
        self.assertEqual(
            promotion._next_minor_version("2.7.4"),
            "2.8.0",
        )

    def test_invalid_base_version_fails_closed(self):
        with self.assertRaises(
            promotion.SkillPromotionStateError
        ):
            promotion._next_minor_version("latest")

    def test_promoted_instructions_preserve_base_guardrails(self):
        value = promotion._promoted_instructions(
            "Base safety instructions",
            "instructions",
            "Approved clarification amendment",
        )
        self.assertTrue(
            value.startswith("Base safety instructions")
        )
        self.assertIn(
            "Approved clarification amendment",
            value,
        )

    def test_activation_requires_exact_base_snapshot(self):
        registry = SkillRegistry()
        registry.register(
            AgentSkill(
                name="request_clarification",
                version="1.0.0",
                description="Clarification",
                instructions="Base instructions",
            )
        )
        row = {
            "skill_name": "request_clarification",
            "base_skill_version": "1.0.0",
            "promoted_skill_version": "1.1.0",
            "base_instructions_snapshot": "Base instructions",
            "promoted_instructions": (
                "Base instructions\n\n"
                "## Approved instruction amendment\n"
                "Ask only necessary questions."
            ),
        }

        promoted = promotion._activate_promotion(
            row,
            registry,
        )

        self.assertEqual(promoted.version, "1.1.0")
        self.assertEqual(
            registry.get("request_clarification").version,
            "1.1.0",
        )

        # Exact restoration is idempotent.
        restored = promotion._activate_promotion(
            row,
            registry,
        )
        self.assertEqual(restored.version, "1.1.0")


if __name__ == "__main__":
    unittest.main()
