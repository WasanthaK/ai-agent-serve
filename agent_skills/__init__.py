from agent_skills.definitions import (
    BUILT_IN_SKILLS,
    DEFAULT_ANALYSIS_SKILLS,
)
from agent_skills.registry import SkillRegistry


skill_registry = SkillRegistry()

for built_in_skill in BUILT_IN_SKILLS:
    skill_registry.register(built_in_skill)


__all__ = (
    "DEFAULT_ANALYSIS_SKILLS",
    "SkillRegistry",
    "skill_registry",
)
