from copy import deepcopy

from agent_skills.base import AgentSkill


class SkillRegistry:
    def __init__(self):
        self._skills = {}

    def register(self, skill: AgentSkill):
        if skill.name in self._skills:
            raise ValueError(f"Skill is already registered: {skill.name}")

        self._skills[skill.name] = skill
        return skill

    def get(self, name: str):
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"Skill is not registered: {name}") from exc

    def names(self):
        return tuple(self._skills)

    def build_instructions(self, skill_names):
        sections = []

        for name in skill_names:
            skill = self.get(name)
            sections.append(
                f"## Skill: {skill.name} v{skill.version}\n"
                f"{skill.instructions.strip()}"
            )

        return "\n\n".join(sections)

    def build_json_schema(self, skill_names):
        properties = {}
        required = []

        for name in skill_names:
            skill = self.get(name)

            for field_name, field_schema in (
                skill.schema_properties.items()
            ):
                if field_name in properties:
                    if properties[field_name] != field_schema:
                        raise ValueError(
                            "Conflicting schema definition for field: "
                            f"{field_name}"
                        )
                else:
                    properties[field_name] = deepcopy(field_schema)

            for field_name in skill.required_fields:
                if field_name not in required:
                    required.append(field_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
