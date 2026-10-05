from copy import deepcopy
from threading import RLock

from agent_skills.base import AgentSkill


class SkillRegistry:
    def __init__(self):
        self._skills = {}
        self._lock = RLock()

    def register(self, skill: AgentSkill):
        with self._lock:
            if skill.name in self._skills:
                raise ValueError(
                    f"Skill is already registered: {skill.name}"
                )

            self._skills[skill.name] = skill
            return skill

    def replace(
        self,
        skill: AgentSkill,
        *,
        expected_version=None,
        expected_instructions=None,
    ):
        with self._lock:
            try:
                current = self._skills[skill.name]
            except KeyError as exc:
                raise KeyError(
                    f"Skill is not registered: {skill.name}"
                ) from exc

            if (
                expected_version is not None
                and current.version != expected_version
            ):
                raise ValueError(
                    "Current skill version does not match expected version"
                )
            if (
                expected_instructions is not None
                and current.instructions.strip()
                != expected_instructions.strip()
            ):
                raise ValueError(
                    "Current skill instructions do not match expected instructions"
                )

            self._skills[skill.name] = skill
            return skill

    def get(self, name: str):
        with self._lock:
            try:
                return self._skills[name]
            except KeyError as exc:
                raise KeyError(
                    f"Skill is not registered: {name}"
                ) from exc

    def names(self):
        with self._lock:
            return tuple(self._skills)

    def versions(self, skill_names):
        with self._lock:
            return {
                name: self._skills[name].version
                for name in skill_names
            }

    def build_instructions(self, skill_names):
        with self._lock:
            sections = []

            for name in skill_names:
                skill = self._skills[name]
                sections.append(
                    f"## Skill: {skill.name} v{skill.version}\n"
                    f"{skill.instructions.strip()}"
                )

            return "\n\n".join(sections)

    def build_json_schema(self, skill_names):
        with self._lock:
            properties = {}
            required = []

            for name in skill_names:
                skill = self._skills[name]

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
                        properties[field_name] = deepcopy(
                            field_schema
                        )

                for field_name in skill.required_fields:
                    if field_name not in required:
                        required.append(field_name)

            return {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            }

    def build_contract(self, skill_names):
        with self._lock:
            return {
                "instructions": self.build_instructions(skill_names),
                "schema": self.build_json_schema(skill_names),
                "versions": self.versions(skill_names),
            }
