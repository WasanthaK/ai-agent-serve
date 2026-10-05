# Quixo ↔ AI Agent Integration Architecture

## Purpose

`ai-agent-serve` is the shared, provider-neutral AI interpretation and transformation runtime for the Quixo platform. It interprets and transforms inbound service requests into structured, reviewable evidence.

Quixo (QuoteService) remains the commercial and system-of-record authority for the governed commercial lifecycle.

This document is the detailed cross-project integration contract. It defines the ownership boundary, the preservation and responsibility invariants, and the target provider-neutral model runtime. It is an architecture contract only: it does not implement a Quixo integration, a model adapter, an external channel change, or any Phase 6 lifecycle behavior, and it does not change production behavior.

## Core architectural invariant

> AI interprets and transforms. Deterministic application code owns authority and state.

> AI output is evidence/proposal, never Quixo commercial authority.

The agent must not independently:

- Approve suppliers
- Alter Quixo membership
- Send, accept, or award quotes
- Create commercial acceptance
- Change Engagement state
- Create or record payment
- Bypass approval requirements

## Ownership boundary

### ai-agent-serve owns

- Authenticated/channel-bound intake normalization
- Durable, lossless inbound-message evidence
- AI interpretation
- Semantic extraction
- Classification
- Summarization
- Structured transformation
- Versioned AI skills
- Model/provider execution
- Model/skill/prompt provenance
- AI-quality evaluation
- Human-review recommendation and escalation evidence

### Quixo / QuoteService owns

- Canonical commercial `ServiceRequest`
- Tenant/company membership and authorization
- Provider/supplier eligibility
- Request distribution
- Quote lifecycle
- Quote approval
- Customer acceptance
- Buyer award
- Engagement lifecycle
- Deposits and variations
- Invoice/payment state
- Audit authority for those business transitions

## Lossless-source contract

> Original meaningful customer input must be durably preserved before semantic model processing.

For every supported channel, the strongest available source evidence must be preserved:

- Website/widget message
- Email subject plus meaningful body
- WhatsApp message/transcript
- Voice transcription plus the source/audio reference where the channel supports it
- Attachment references
- External message/thread identifiers
- Channel/source metadata required for traceability

An AI-produced summary or description must never overwrite or become the sole surviving representation of the customer's original request.

On model failure, the original source must remain available for human handling.

This contract extends the existing durable inbound-message persistence from Phase 4D (`inbound_messages`) and the design principle that "customer messages are stored before downstream AI processing". It is a preservation invariant, not a new persistence implementation.

## Deterministic vs AI responsibility

Deterministic code handles mechanical validation and governance; AI skills own semantic interpretation.

### Deterministic code MAY

- Authenticate/verify channels
- Verify signatures/secrets
- Sanitize unsafe markup
- Decode transport payloads
- Parse JSON/protocol envelopes
- Validate email/phone syntax
- Enforce lengths/types/schema
- Perform idempotency checks
- Enforce authorization
- Enforce state transitions
- Enforce provider eligibility
- Enforce limits/business invariants

### AI skills own semantic interpretation

- Customer intent
- Service/category classification
- Urgency interpretation
- Meaningful location interpretation
- Job scope
- Quantities/equipment/context
- Constraints
- Availability
- Special instructions
- Summaries
- Clarification questions
- Request to quote-draft suggestions

### No low-fidelity semantic fallback

> Do not introduce regex/keyword semantic classifiers as an AI-failure fallback.

If semantic AI processing fails:

- Preserve the source
- Record the failure
- Enter retry/human-review handling as appropriate
- Do not silently substitute a lower-fidelity semantic parser

This preserves the existing Phase 4C behavior in which a model-call failure is recorded, the stored message survives, and the endpoint fails closed (HTTP `502`) rather than guessing.

## Provider-neutral AI runtime

### Current reality

The skill and inbound architecture is already provider-neutral, but the inference implementation is still directly coupled to a single provider and a fixed model:

- `app.py` imports the OpenAI SDK and constructs an OpenAI client from an environment key
- The analysis call invokes a fixed model identifier directly

This is the recorded gap this contract addresses. The target concepts below do NOT exist yet.

### Target concepts (not yet implemented)

- `AiModelProvider` — invokes one model provider; provider-specific API translation only
- `AiModelRegistry` — known/configured providers and models; capability metadata
- `AiModelRouter` — resolves a skill/task to a configured provider and model

Business/skill code must not instantiate an OpenAI/Gemini/Ollama SDK directly. None of these concepts is implemented in this documentation task.

## Model-routing policy

Model selection is operational configuration, not embedded in skill/business code. Target routing semantics:

- Platform default provider/model
- Per-skill/task override
- Explicit disabled/unavailable provider state
- Optional candidate/shadow model
- Future providers such as OpenAI, Gemini, and Ollama/local inference

Example concept:

- `customer_request_interpretation` to a provider/model configuration
- `request_to_quote_draft` to potentially a different provider/model
- `safety_triage` to potentially a different provider/model

Changing provider/model must not require changes to Quixo workflow or business logic.

## Provenance and evaluation

Extending the existing skill/tool version provenance and model-call metrics, evidence for each AI transformation should include, where available:

- Provider
- Model
- Skill
- Skill version
- Transformation/schema version
- Instruction/prompt version or stable identifier
- Started/completed timing
- Latency
- Success/failure
- Schema-valid status
- Token/usage metadata where the provider supplies it
- Cost metadata where practical
- Fallback/routing decision
- Safe correlation/request/inbound reference, without exposing secrets

Secret API keys and unsafe raw provider diagnostics must not be persisted.

## Human-correction evidence

Model self-confidence alone is not sufficient quality evidence. Where a human reviews an AI transformation, capture bounded evaluation evidence such as:

- Accepted unchanged
- Accepted after correction
- Rejected
- Fields corrected
- Clarification required

This should eventually support per-provider/model/skill quality comparison. The storage schema is deliberately not defined in this documentation task.

## Shadow evaluation

A candidate model may receive the same permitted transformation input as the production-selected model, but it has **zero workflow authority**.

It must not:

- Execute tools
- Change state
- Notify anyone
- Create external actions

Candidate output is stored and evaluated separately. Promotion of a candidate model requires reviewed evidence.

> Production behaviour must never change solely because of unreviewed model output.

## Initial shared skills

These are architectural targets that extend the existing skill model. They are not registered or implemented in this task.

### `customer_request_interpretation`

Input:

- Normalized/lossless inbound message
- Permitted business context

Output concept:

- Structured customer/request information
- Category/service
- Urgency
- Location
- Requirements
- Quantities/equipment
- Constraints
- Availability
- Special instructions
- Missing-information questions

No Quixo state authority.

### `request_to_quote_draft`

Input concept:

- Original request
- Structured request
- Clarifications
- Permitted company context
- Products/services
- Company AI business instructions
- Relevant inspection/context when explicitly provided

Output concept:

- Suggested title
- Suggested scope
- Suggested quote line structure
- Assumptions
- Exclusions
- Missing information
- Review flags

It must not send a quote or approve pricing.

## Quixo rollout gates

Existing Quixo production intake paths must NOT be cut over merely because an agent adapter exists. Before any channel is switched to the agent interpretation runtime, require:

- Contract defined
- Lossless source preservation proven
- Idempotency/retry proof
- Schema validation
- Provenance
- Failure behavior
- Authority boundary tests
- Comparison against the current path
- Controlled pilot/shadow evidence where practical
- Explicit rollout decision

Roll out channel by channel.

## Relationship to the ai-agent-serve roadmap

- Phase 6 (service-delivery coordination) remains the current operational-lifecycle lane.
- This architecture is a cross-cutting runtime/integration lane required before any Quixo AI cutover; it is not a numbered phase and it does not renumber or invalidate Phase 6.
- It does not imply multi-tenant commercial production readiness.
- It does not imply outbound messaging is enabled.
- It does not imply the provider-neutral model abstraction is complete.
- It does not imply Quixo has been cut over.

The ai-agent-serve Technical Roadmap remains the canonical source for phase sequencing and status. This document is the canonical detailed integration contract.