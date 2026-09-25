# Skills Architecture

## Purpose

Skills package reusable service-delivery knowledge, schemas and policies separately from API routes and concrete tools.

A skill describes how the agent should reason about one business capability. A tool performs an operation. Workflow state determines whether either capability may be used.

## Skill contract

Each `AgentSkill` defines:

- Stable name
- Semantic version
- Business description
- Model instructions
- Structured-output fields
- Required fields
- Permitted workflow states
- Permitted tools

Skills are immutable after construction.

## Registry controls

The `SkillRegistry`:

- Rejects duplicate skill names
- Retrieves skills by stable name
- Composes instructions in a deterministic order
- Builds one strict JSON schema
- Rejects conflicting field definitions
- Rejects undeclared required fields

The OpenAI call continues to use `additionalProperties: false`.

## Built-in skills

### Request intake

Produces intent, category, summary, urgency and next action.

### Request clarification

Identifies essential missing information and produces focused follow-up questions.

### Safety triage

Determines when a request must enter human review. Missing information alone is not treated as a safety escalation.

### Customer communication

Applies plain-language and non-disclosure rules to customer-facing questions.

## Skills and tools

Skills may declare the tools they are permitted to use. This metadata is the foundation for centrally enforced skill-to-tool authorization in a later milestone.

The current follow-up tool remains restricted by workflow state in the API.

## Compatibility

Phase 4A intentionally preserves the existing API response schema and workflow states. The source of the model instructions and JSON schema changes; observable endpoint behaviour should not.

## Testing

Run the registry unit tests:

```bash
python3 -m unittest tests/test_skill_registry.py -v
```

Run the Phase 3 end-to-end regression test against the live containers:

```bash
python3 tests/smoke_phase3.py
```

A skill change is not complete until both its unit tests and the relevant end-to-end workflow tests pass.
