# Phase 4C version provenance

## Purpose

The agent records the exact skill and tool versions that contributed to auditable workflow events.

This provenance is stored in existing append-only `agent_events.details` JSON. No database migration is required.

## Skill provenance

The built-in analysis skills already declare semantic versions as part of the `AgentSkill` contract.

For the default analysis pipeline, the application resolves the active skill-version map from the skill registry and records it on:

- `request_created`
- `request_reanalysed`

The event detail field is:

```json
{
  "skill_versions": {
    "request_intake": "1.0.0",
    "request_clarification": "1.0.0",
    "safety_triage": "1.0.0",
    "customer_communication": "1.0.0"
  }
}
```

The map describes the skill versions used for that specific analysis event. Historical events therefore retain their original provenance even after a skill version changes later.

## Tool provenance

Registered tools now pair their handler with an explicit version in the tool registry.

The tool version is recorded on:

- `tool_started`
- `tool_completed`
- `tool_failed`

For example:

```json
{
  "tool": "prepare_customer_follow_up",
  "tool_version": "1.0.0"
}
```

The execution path and version lookup use the same registry entry so version metadata cannot silently drift from the registered handler.

## Privacy and audit scope

Version provenance contains only controlled identifiers and version strings.

It does not add:

- customer names or messages
- prompts or model outputs
- API keys or credentials
- exception messages
- request payloads

Existing correlation IDs, actors, timestamps, and workflow event types continue to provide the surrounding audit context.

## Compatibility

This capability does not change:

- workflow states or transitions
- authorization or permission checks
- model prompts or schemas
- tool authority
- request or message table schemas
- existing API response contracts

Database helper parameters remain optional so existing internal callers and tests that do not represent a production analysis path remain compatible.

## Validation

Automated coverage verifies:

- default analysis skills expose explicit versions
- the registered tool exposes an explicit version
- `request_created` records supplied skill versions
- `request_reanalysed` records supplied skill versions
- tool lifecycle events record the tool version
- version metadata remains compatible with event-privacy expectations

## Next Phase 4C item

The next roadmap item is health and readiness checks.
