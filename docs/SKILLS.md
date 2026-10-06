# Skills Architecture

## Purpose

Skills package reusable domain expertise, service-delivery knowledge, schemas and policies separately from API routes and concrete tools.

The long-term goal is not generic classification. Each selectable domain should evolve toward an expert skill pack capable of turning imperfect real-world requirements into a commercially useful scope while representing uncertainty truthfully.

A skill describes how the agent should reason. A tool performs an operation. Workflow state and deterministic policy determine whether either capability may be used. Transactional authority remains in the owning Quixo product (for example SendQuote, RequestQuote or Marketplace), never in a skill.

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

## Service skill catalogue

Workflow skills are composed with a selected domain profile. The catalogue
contains 47 selectable service profiles and seven non-selectable group headers.
Each profile defines a stable slug, label, optional group, display order,
version, focused intake topics and domain-specific escalation topics.

The 13 trade and construction profiles belong to the non-selectable `trades`
group.

The catalogue validates unique slugs, valid group references, selectability
and required intake topics. This data-driven model avoids 47 nearly identical
Python modules while keeping every domain profile independently testable.

The request-intake schema uses the 47 service slugs as a strict JSON Schema
enum. The model therefore returns a stable machine-readable category such as
`plumbing` or `airport-transfers`, never a group header or an invented label.

At runtime the catalogue contributes a compact instruction block containing
the intake and escalation topics for every profile. Once a category is
selected, the agent applies only that profile. Intake topics guide relevant
clarification rather than forcing a questionnaire.

The complete machine-readable taxonomy is available from:

```text
GET /service-catalog
```

This endpoint is read-only and can be consumed by Quixo forms, channel
adapters and future provider-routing components.

## Compatibility

Phase 4A intentionally preserves the existing API response schema and workflow states. The source of the model instructions and JSON schema changes; observable endpoint behaviour should not.

## Testing

Run the registry unit tests:

```bash
python3 -m unittest tests/test_skill_registry.py -v
```

Run the catalogue tests:

```bash
python3 -m unittest tests/test_service_catalog.py -v
```

Run the Phase 3 end-to-end regression test against the live containers:

```bash
python3 tests/smoke_phase3.py
```

Run the Phase 4 live skill test:

```bash
python3 tests/smoke_phase4.py
```

A skill change is not complete until both its unit tests and the relevant end-to-end workflow tests pass.


## Domain Expert Skill Packs

A mature domain skill may define:

- domain ontology and terminology
- intake/scoping topics
- diagnostic reasoning patterns
- clarification strategy
- work-breakdown patterns
- materials/equipment concepts
- labour concepts
- typical dependencies
- assumptions/exclusions guidance
- safety and compliance escalation
- pricing-readiness rules
- inspection-required rules
- environmental/context dependencies
- confidence/evidence rules
- domain regression fixtures
- known failure modes

Examples include plumbing, HVAC, electrical, roofing, exterior painting, landscaping, automotive and event services.

Domain skill packs remain independently versioned and regression-tested.

## Context dependencies

A domain skill may declare external context it knows how to interpret, for example weather, wind, humidity, heat, flood/fire alerts, tides or daylight.

The skill interprets context. It does not gain authority to reschedule, commit price, contact a customer/provider or alter Quotes transactional state.

## Expert output contracts

The target architecture defines two related contracts in
`docs/AGENT-QUOTES-BOUNDARY.md`.

### Requirement Intelligence Package

Customer/request-side, price-neutral output used by RequestQuote, Marketplace and
connectors during or after intake.

It must not invent provider prices.

### Commercial Proposal Package

Provider-side expert output used by SendQuote/provider workflows. It may contain
clearly-labelled pricing suggestions or estimates only where policy permits, while
the provider/human and SendQuote remain authoritative for final commercial values,
totals, approval and sending.

Both contracts preserve the distinction between:

- supplied facts
- authoritative platform facts
- expert inference
- assumptions
- estimates
- unknown/missing information
- safety-critical uncertainty

Product adapters translate approved package data into supported Quixo API
contracts. Skills must never depend directly on another product's database models.

## Product consumers

A domain skill can be consumed independently by:

- RequestQuote
- Marketplace
- SendQuote
- selected connectors
- future separate products such as Task Scheduler/Workforce

The same domain expertise may be used at different stages with different authority
and output constraints. For example, RequestQuote remains price-neutral while
SendQuote may request provider-side proposal intelligence.
