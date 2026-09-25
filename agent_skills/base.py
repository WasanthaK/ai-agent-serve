from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class AgentSkill:
    name: str
    version: str
    description: str
    instructions: str
    schema_properties: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    required_fields: tuple[str, ...] = ()
    permitted_states: frozenset[str] = frozenset()
    permitted_tools: frozenset[str] = frozenset()

    def __post_init__(self):
        if not self.name:
            raise ValueError("Skill name cannot be empty")
        if not self.version:
            raise ValueError("Skill version cannot be empty")

        unknown_required = set(self.required_fields) - set(
            self.schema_properties
        )
        if unknown_required:
            raise ValueError(
                "Required fields must be declared in schema_properties: "
                f"{sorted(unknown_required)}"
            )
