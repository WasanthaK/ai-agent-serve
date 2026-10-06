import unittest

from agent_skills import DEFAULT_ANALYSIS_SKILLS, skill_registry
from agent_skills.base import AgentSkill
from agent_skills.registry import SkillRegistry


class SkillRegistryTests(unittest.TestCase):
    def test_built_in_skills_are_registered_without_changing_default_analysis(self):
        self.assertEqual(
            skill_registry.names(),
            DEFAULT_ANALYSIS_SKILLS + ("provider_routing", "requirement_intelligence"),
        )
        self.assertNotIn("provider_routing", DEFAULT_ANALYSIS_SKILLS)
        self.assertNotIn("requirement_intelligence", DEFAULT_ANALYSIS_SKILLS)

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

    def test_requirement_intelligence_is_separate_from_legacy_analysis(self):
        skill = skill_registry.get("requirement_intelligence")

        self.assertEqual(skill.version, "1.0.0")
        self.assertEqual(skill.permitted_tools, frozenset())
        self.assertIn("never invent provider pricing", skill.instructions)

    def test_routing_skill_cannot_rank_select_or_mutate_providers(self):
        skill = skill_registry.get("provider_routing")

        self.assertEqual(skill.version, "1.0.0")
        self.assertEqual(skill.permitted_tools, frozenset())
        self.assertIn("Never invent, add, remove, rank, select", skill.instructions)

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

    def test_replace_requires_exact_expected_base(self):
        registry = SkillRegistry()
        original = AgentSkill(
            name="example",
            version="1.0.0",
            description="Example",
            instructions="Base instructions",
        )
        registry.register(original)

        promoted = AgentSkill(
            name="example",
            version="1.1.0",
            description="Example",
            instructions="Base instructions\n\nApproved amendment",
        )
        registry.replace(
            promoted,
            expected_version="1.0.0",
            expected_instructions="Base instructions",
        )
        self.assertEqual(registry.get("example").version, "1.1.0")

        with self.assertRaises(ValueError):
            registry.replace(
                original,
                expected_version="1.0.0",
            )

    def test_build_contract_snapshots_versions_schema_and_instructions(self):
        registry = SkillRegistry()
        registry.register(
            AgentSkill(
                name="example",
                version="2.3.0",
                description="Example",
                instructions="Use the reviewed behavior.",
                schema_properties={"value": {"type": "string"}},
                required_fields=("value",),
            )
        )

        contract = registry.build_contract(("example",))
        self.assertEqual(contract["versions"], {"example": "2.3.0"})
        self.assertIn("example v2.3.0", contract["instructions"])
        self.assertEqual(contract["schema"]["required"], ["value"])

    def test_customer_communication_restricts_tools(self):
        skill = skill_registry.get("customer_communication")

        self.assertEqual(
            skill.permitted_tools,
            frozenset({"prepare_customer_follow_up"}),
        )


if __name__ == "__main__":
    unittest.main()
