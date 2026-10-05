# Agent Architecture

> **Current target architecture.** The original Phase 1–3 runtime was a standalone
> request/workflow prototype. That implementation remains valuable and is still
> present, but it no longer defines product ownership.
>
> Canonical product-family boundary: `docs/AGENT-QUOTES-BOUNDARY.md`.

## Design principle

The Expert Agent Platform is an independently deployable intelligence service for
the Quixo product family.

It provides domain expertise, structured reasoning, clarification, safety/context
analysis, proposal intelligence, provenance and controlled learning.

It does not become SendQuote, RequestQuote, Marketplace, Messaging or a future Task
Scheduler.

Large-model inference may be cloud-hosted or provided by separate local/GPU
infrastructure without changing product contracts.

## Target topology

```text
       Web / Widget / Email / WhatsApp / Voice / API
                         |
              +----------+----------+
              |                     |
              v                     v
         RequestQuote           SendQuote
              ^                     ^
              |                     |
          Marketplace               |
              ^                     |
              |                     |
              +----------+----------+
                         |
                         v
               Expert Agent Platform

Marketplace -> RequestQuote for sourcing/request flow.
Marketplace, RequestQuote and SendQuote all consume Expert Agent intelligence.
Connectors may call the Expert Agent before a canonical product record exists.

Future Task Scheduler/Workforce is a separate product/project and may consume the
same Expert Agent through versioned contracts.
```

## Invocation modes

### Pre-record intelligence

The agent can interpret conversational/connector input before a canonical
ServiceRequest or Quotation exists.

This is important for voice, widget, email and WhatsApp intake.

### Post-record intelligence

A Quixo product can provide a stable external reference plus the minimum authorised
context for deeper expert analysis, clarification or proposal preparation.

The agent never acquires ownership of that external record.

## Expert outputs

### Requirement Intelligence Package

Price-neutral request-side intelligence for customer/buyer intake.

### Commercial Proposal Package

Provider-side proposal intelligence for SendQuote/provider review.

Both are strict, versioned schemas and distinguish facts, inference, assumptions,
estimates, unknowns and safety-critical uncertainty.

## Workflow state

Agent workflow state is **analysis/orchestration state only**.

States such as:

- `needs_information`
- `awaiting_human_review`
- `ready`
- legacy `approved/rejected/actioned` prototype states

must not be interpreted as authoritative Quixo business state.

SendQuote/RequestQuote/Marketplace remain authoritative for their own lifecycle
states.

## Messaging and conversation evidence

Quixo Messaging/product connectors are the authoritative business communication
systems.

Legacy `agent_messages`, inbound persistence and conversation replay remain useful
for prototype compatibility, retry/reanalysis and learning evidence, but must not
become a second canonical conversation ledger.

Future integration should prefer stable message/conversation references plus only
the bounded content needed for reproducible agent analysis.

## Human authority

The existing Quixo rule remains non-negotiable:

**AI suggests; humans decide.**

The Expert Agent may interpret, structure, compare and recommend within policy. It
does not autonomously finalize prices, send quotes, select commercial winners,
award procurement or change another product's state without an explicitly
authorised deterministic action.

## Controlled tools

Agent tools remain explicit, state-aware and auditable.

A tool can call an external Quixo API only when:

- the contract is versioned
- the caller/acting context is authenticated
- the tool has explicit authority
- idempotency/correlation are defined
- the action is allowed in both agent policy and the owning product
- required human approval is present

No tool may bypass product APIs through direct database access.

## Agent persistence

The agent database owns only agent concerns:

- analysis/provenance
- skill/model versions
- evaluations
- regression/promotion evidence
- correlation
- bounded retry/recovery
- agent audit/telemetry
- temporary/prototype compatibility data during migration

It does not own provider, RFQ, quotation, marketplace, messaging or workforce
transactional truth.

## Existing runtime API

The current FastAPI endpoints and persistence model remain compatibility surfaces
from the standalone prototype. They should be migrated incrementally rather than
deleted in one change.

The existing endpoints include direct analysis, request/reanalysis, operator review
and tool execution. New product integrations should prefer versioned expert
contracts rather than extending the prototype request API into a new Quixo system
of record.

## Failure isolation

The safe-distance architecture requires:

- Quixo products remain transactionally correct if the Expert Agent is unavailable
- degraded/manual product paths exist where appropriate
- agent failure cannot corrupt product state
- product failures do not corrupt skill/evaluation history
- retries are bounded/idempotent
- each side can deploy and roll back independently

## Learning architecture

```text
real requirement
 -> expert analysis
 -> human/provider correction
 -> product outcome evidence
 -> human evaluation
 -> improvement proposal
 -> regression
 -> human-controlled promotion
 -> new skill version
```

Production behaviour must never change solely because of unreviewed model output.

## Context intelligence

Domain skills may consume external evidence such as weather, wind, humidity, heat,
flood/fire warnings, tides, daylight or access conditions.

The agent interprets that evidence. Deterministic policy decides whether it is
informational, review-required, rescheduling-recommended or safety-escalated.

The agent does not silently alter another product's schedule or commercial
commitment.

## Future separate products

Task Scheduler / Workforce / Service Delivery will be separate products/projects.

The Expert Agent can provide those products with domain intelligence such as:

- job requirements
- required skills/certifications
- likely duration/risk
- environmental constraints
- execution-readiness advice

but does not own staff, schedules, tasks, shifts or workforce execution state.

## Verification

Existing Phase 3/4 tests continue to protect the current runtime during migration.
New product integrations must additionally use contract tests on both sides of each
versioned boundary.
