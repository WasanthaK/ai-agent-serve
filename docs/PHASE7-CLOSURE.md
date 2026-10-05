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
