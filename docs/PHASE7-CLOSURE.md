# Phase 7 — Closure and learning

Phase 7 begins only after governed delivery completion.

## Satisfaction follow-up preparation

The first closure slice prepares one durable customer satisfaction follow-up for a completed delivery.

Preparation requires:

- the same request to remain in the existing `actioned` workflow state;
- a persisted delivery-status record in `completed`;
- operator `decide`; and
- no model-created authority.

The follow-up contains a deterministic question:

> How satisfied are you with the completed service? Please rate your experience from 1 to 5.

The durable record carries:

- request ID;
- completed delivery-status ID;
- provider ID;
- purpose `customer_satisfaction`;
- rating scale 1–5;
- unresolved destination channel/address;
- status `prepared`;
- preparing operator; and
- creation timestamp.

Repeated preparation returns the same record and does not duplicate the audit event.

Retrieval requires operator `read`.

This slice does not:

- infer or resolve a customer destination;
- send email, WhatsApp, SMS, or another message;
- record a satisfaction response;
- trigger a review request;
- create a complaint/rework case;
- change request or delivery state; or
- perform any external action.

The PostgreSQL lifecycle proof extends the completed delivery flow through satisfaction follow-up preparation and verifies one durable record, stable retry identity, one audit event, unresolved destination, no response, and no external send.


## Satisfaction response ingestion

A prepared satisfaction follow-up may receive exactly one durable response evidence record.

The response is operator-recorded evidence and requires:

- the same actioned request;
- the exact prepared follow-up ID;
- an integer rating from 1 through 5;
- a timezone-aware response timestamp that cannot be in the future or predate follow-up creation;
- an explicit response evidence source;
- optional customer comment; and
- operator `decide`.

The first valid response moves the follow-up from `prepared` to `responded`.

An exact retry with the same evidence is idempotent. A conflicting retry fails closed and preserves the original response.

The audit event records the rating and evidence source while explicitly stating that no review request, complaint, rework case, or external action was created.

This slice does not infer sentiment beyond the submitted rating and does not automatically trigger downstream closure workflows.


## Public review-request preparation

A public-review request may be prepared only after satisfaction evidence has been recorded.

Preparation requires:

- the same actioned request;
- the exact satisfaction follow-up in `responded` state;
- an explicit operator reason; and
- operator `decide`.

The review request is deliberately **not rating-gated**. Ratings from 1 through 5 are equally eligible for preparation. The system does not selectively ask only satisfied customers for public reviews.

The durable record contains:

- request ID;
- satisfaction follow-up ID;
- provider ID;
- deterministic review-request message;
- unresolved target platform and target URL;
- unresolved outbound destination channel/address;
- status `prepared`;
- preparation reason/operator; and
- creation timestamp.

An exact retry is idempotent. Conflicting preparation evidence fails closed.

The audit event snapshots the satisfaction rating only as evidence and explicitly records `rating_gated = false`.

This slice does not:

- choose a review platform;
- resolve or validate a review URL;
- send a review request;
- change request/delivery state;
- create a complaint or rework case; or
- perform any external action.

The PostgreSQL lifecycle proof intentionally uses a 1/5 satisfaction rating and still prepares the review request, proving the workflow is not rating-gated.


## Complaint and rework escalation foundation

Recorded satisfaction evidence may be escalated into explicit human-owned closure cases.

Supported escalation kinds are deliberately limited to:

- `complaint`;
- `rework`.

Each request may have at most one escalation of each kind.

Creation requires:

- the same request to remain `actioned`;
- the exact satisfaction follow-up in `responded` state;
- explicit priority: `normal`, `high`, or `urgent`;
- an explicit human-authored reason; and
- operator `decide`.

Escalation is **not automatically inferred from satisfaction rating**. A low rating is evidence only. The operator decides whether a complaint or rework case should exist.

A rework escalation does not reopen the completed delivery and does not authorize or dispatch new service work.

Exact retries return the existing same-kind escalation. Conflicting evidence for an existing kind fails closed.

The audit event explicitly records:

- the observed satisfaction rating;
- `auto_triggered = false`;
- `delivery_reopened = false`;
- `rework_dispatched = false`;
- `notification_sent = false`; and
- `external_action_performed = false`.

The PostgreSQL lifecycle proof creates both complaint and rework escalations from the same 1/5 satisfaction evidence, preserves completed delivery and actioned request state, and proves that neither escalation dispatches or reopens work.


## Outcome measurement

Outcome measurement is a read-only factual projection over persisted service-delivery and closure evidence.

`GET /requests/{request_id}/outcome-measurement` requires operator `read`.

The projection reports:

- request and provider identity;
- delivery status and completion timestamp;
- whether satisfaction evidence exists;
- recorded satisfaction rating and response timestamp;
- whether a public-review request has been prepared;
- delivery exception count;
- total and open intervention counts;
- complaint presence; and
- rework presence.

The projection deliberately does **not** compute:

- provider score;
- provider rank;
- success/failure label;
- training signal;
- automated policy change; or
- any production action.

Returned control fields make that boundary explicit:

- `score = null`;
- `provider_rank = null`;
- `policy_change_applied = false`;
- `training_signal_applied = false`; and
- `external_action_performed = false`.

This slice creates no database mutation and emits no operational action. It is evidence for later human-reviewed skill evaluation and policy work, not authority to change production behavior.

The PostgreSQL lifecycle proof reconstructs the current full closure facts—including completed delivery, 1/5 satisfaction evidence, two delivery exceptions, intervention history, prepared review request, complaint and rework—without scoring or ranking the provider.


## Skill evaluation against real cases

A skill evaluation is a human-authored review of a skill/version that is proven to have run on a persisted real request.

Each evaluation is bound to:

- the request ID;
- one exact analysis-event ID;
- event type `request_created` or `request_reanalysed`;
- one skill name present in that event's persisted `skill_versions` map; and
- the historical skill version recorded for that event.

This avoids evaluating a current skill version against an older case unless the audit trail proves that exact version ran on the case.

Creation requires:

- operator `decide`;
- explicit verdict: `pass`, `needs_review`, or `fail`; and
- explicit evaluator notes.

At evaluation time, the service snapshots the current factual outcome projection for that request. The snapshot may include delivery completion, satisfaction evidence, review preparation, exception/intervention counts, complaint, and rework facts.

Each analysis-event/skill pair may have at most one immutable evaluation. Exact retries return the existing record; conflicting verdict/notes/evaluator evidence fails closed.

The recorded evaluation explicitly states that it does **not**:

- apply a training signal;
- change a skill version;
- change policy;
- promote a skill;
- change production behaviour; or
- perform an external action.

The PostgreSQL lifecycle proof evaluates the exact `request_intake` v1.0.0 provenance from a real persisted `request_created` event against the existing factual closure outcome, proves exact retry identity, rejects a conflicting verdict, and verifies no automated learning or promotion side effect.
