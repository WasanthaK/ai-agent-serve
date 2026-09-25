import unittest

from agent_skills import DEFAULT_ANALYSIS_SKILLS, skill_registry
from agent_skills.base import AgentSkill
from agent_skills.registry import SkillRegistry


class SkillRegistryTests(unittest.TestCase):
    def test_built_in_skills_are_registered(self):
        self.assertEqual(
            skill_registry.names(),
            DEFAULT_ANALYSIS_SKILLS,
        )

    def test_analysis_schema_is_strict_and_complete(self):
        schema = skill_registry.build_json_schema(
            DEFAULT_ANALYSIS_SKILLS
        )

        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]),
            {
                "intent",
                "category",
                "summary",
                "urgency",
                "next_action",
                "needs_human_review",
                "missing_information",
                "follow_up_questions",
            },
        )
        self.assertEqual(len(schema["properties"]["category"]["enum"]), 47)
        self.assertIn("plumbing", schema["properties"]["category"]["enum"])
        self.assertNotIn("home-services", schema["properties"]["category"]["enum"])

    def test_duplicate_skill_name_is_rejected(self):
        registry = SkillRegistry()
        skill = AgentSkill(
            name="example",
            version="1.0.0",
            description="Example skill",
            instructions="Example instructions",
        )

        registry.register(skill)

        with self.assertRaises(ValueError):
            registry.register(skill)

    def test_conflicting_schema_fields_are_rejected(self):
        registry = SkillRegistry()
        registry.register(
            AgentSkill(
                name="first",
                version="1.0.0",
                description="First",
                instructions="First",
                schema_properties={"value": {"type": "string"}},
                required_fields=("value",),
            )
        )
        registry.register(
            AgentSkill(
                name="second",
                version="1.0.0",
                description="Second",
                instructions="Second",
                schema_properties={"value": {"type": "boolean"}},
                required_fields=("value",),
            )
        )

        with self.assertRaises(ValueError):
            registry.build_json_schema(("first", "second"))

    def test_customer_communication_restricts_tools(self):
        skill = skill_registry.get("customer_communication")

        self.assertEqual(
            skill.permitted_tools,
            frozenset({"prepare_customer_follow_up"}),
        )


if __name__ == "__main__":
    unittest.main()
