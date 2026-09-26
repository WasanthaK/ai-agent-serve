"""Deterministic workflow policy applied after model analysis."""


def enforce_safety_precedence(result):
    """Ensure human-review safety decisions cannot be blocked by clarification."""
    normalized = dict(result)
    if normalized.get("needs_human_review"):
        normalized["missing_information"] = []
        normalized["follow_up_questions"] = []
    return normalized
