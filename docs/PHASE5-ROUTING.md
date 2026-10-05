# Phase 5B provider routing

## Purpose

Phase 5B converts deterministic provider eligibility into an explicit, unranked candidate set and explains that set using only the eligibility facts already proven by application code.

Routing does not grant authority and does not change provider state. It consumes only persisted provider facts enforced by the Phase 5A provider-management foundation.

## Eligibility boundary

`provider_routing.build_provider_candidates(service_slug, area_key)` delegates eligibility to `provider_directory.list_eligible_providers_for_service_and_area(...)`.

A provider can appear in the candidate set only when all of these persisted facts are true:

1. provider approval status is `approved`;
2. the provider has the requested canonical service capability;
3. the provider has the exact requested coverage-area key;
4. availability status is `available`; and
5. compliance status is `compliant`.

The routing layer does not infer any of those facts and does not broaden coverage when no exact match exists.

## Candidate contract

A non-empty candidate result has:

- `status = eligible_candidates`
- the canonical `service_slug`
- the exact `area_key`
- the fixed eligibility basis
- an ordered list of candidate provider IDs and display names
- `candidate_count`
- `requires_human_review = false`

The order is the stable order returned by the provider directory. It is not a score or ranking.

An empty result has:

- `status = no_eligible_provider`
- an empty candidate list
- `candidate_count = 0`
- `requires_human_review = true`

The application must not silently expand geography, relax compliance, treat unknown availability as available, or invent a provider when the candidate set is empty.

## Deterministic explanation contract

`provider_routing.explain_provider_candidates(service_slug, area_key)` constructs the candidate set internally. It does not accept a caller-supplied or model-supplied provider list.

For each eligible candidate it explains only the five facts already guaranteed by candidate construction:

- persisted approval is `approved`;
- exact requested service capability is present;
- exact requested coverage-area key is present;
- persisted availability is `available`; and
- persisted compliance is `compliant`.

Explanation output explicitly states:

- `ranked = false`; and
- `selected_provider_id = null`.

The explanation layer therefore cannot convert explanation into ranking or selection.

When no provider qualifies, the explanation is deliberately generic: no provider satisfied all required eligibility conditions for the exact service and area. It does not guess which provider failed which eligibility check because ineligible-provider evidence is not part of this contract.

## Skill boundary

`provider_routing` is registered as a built-in skill, version `1.0.0`.

It is intentionally separate from `DEFAULT_ANALYSIS_SKILLS`, so existing request-intake analysis and its JSON schema remain unchanged.

The skill must never invent, add, remove, rank, select, approve, suspend, or contact providers.

Candidate construction and explanation register no write-capable model tool. Human provider selection is exposed only through authenticated operator routes and is never available as model authority.

## Ranking-policy governance

Provider ranking is enabled only for the governed response-reliability factor and remains runtime-gated by ranking readiness.

The current provider facts — approval, service capability, exact coverage area, availability and compliance — are eligibility gates. They must not be converted into ranking points because every candidate has already passed them.

`provider_ranking_policy.py` defines the governance contract that must be satisfied before ranking can be enabled.

Any future ranking factor must have all of the following before activation:

- an explicit deterministic evidence source;
- a fixed ranking direction;
- a versioned normalization rule;
- a defined missing-data rule;
- a freshness rule; and
- an integer weight.

When ranking is enabled, active factor weights must total exactly 100.

The policy catalogue currently permits only future operational factors for which deterministic evidence could be added later:

- `confirmed_capacity`
- `confirmed_start_time`
- `distance_km`
- `response_reliability`
- `service_quality`

The active ranking policy uses only `response_reliability` at 100% weight. Execution still fails closed unless the readiness guard proves at least two current eligible providers and sufficient governed history for every current candidate.

Explicitly prohibited ranking inputs include:

- any eligibility gate;
- provider ID or provider creation order;
- model preference;
- protected characteristics;
- undisclosed commercial priority.

Provider selection remains `human_only`. Ranking ties require `human_review`; the system must not silently break ties using IDs, creation order or model judgment.

### Historical response reliability evidence

`provider_response_reliability.py` records provider response opportunities and provider responses as separate durable records.

The metric intentionally measures responsiveness rather than willingness to quote:

- an on-time quote counts as an on-time response;
- an on-time decline also counts as an on-time response;
- a late response is completed history but is not on time;
- no response after the deadline is completed history and is not on time;
- an opportunity whose deadline has not passed and has no response is still open and is excluded.

The v1 evidence policy uses:

- a rolling 90-day history window;
- a minimum of 5 completed opportunities;
- an integer reliability scale from 0 to 10,000 basis points;
- `reliability_bps = floor(on_time_responses * 10000 / completed_opportunities)`.

Providers with fewer than five completed opportunities return `insufficient_history` and no reliability score. They are not assigned a low score.

The provider-response opportunity ID is intentionally opaque in this slice. The future RFQ handoff can bind it to the provider-specific RFQ invitation identity without changing the reliability calculation contract.

The response-reliability metric is the sole active ranking factor. Providers with insufficient history remain unscored and cause the readiness guard to fail closed.

## Human-approved provider selection

Provider selection is an explicit human decision and is separate from model routing explanation and future ranking.

`POST /requests/{request_id}/provider-selection` requires the existing operator `decide` permission. `GET /requests/{request_id}/provider-selection` requires `read`.

Selection is permitted only when the request is actionable:

- `ready`; or
- `approved`.

The selected providers must be a non-empty subset of the deterministic eligible-provider set for the exact canonical service and exact area at decision time.

The decision is persisted as an immutable set, not an ordered list. Canonical sorting is used only for storage and comparison and must not be interpreted as ranking.

The same transaction:

- locks the request;
- reconstructs and locks the relevant eligibility rows;
- snapshots the full eligible-provider ID set;
- stores the selected provider set, human actor and optional reason; and
- appends `provider_selection_recorded` to the request audit history.

An exact retry returns the original immutable decision even if provider eligibility changes later. A different retry fails closed rather than silently replacing the human decision.

The selection endpoint does not change request status, contact providers, dispatch work, or activate ranking.

## RFQ handoff foundation

RFQ preparation starts only after an immutable human provider selection exists.

`POST /requests/{request_id}/rfq-handoff` requires the existing operator `decide` permission. `GET /requests/{request_id}/rfq-handoff` requires `read`.

Preparation creates exactly one durable RFQ snapshot per request and exactly one provider-specific handoff identity per selected provider.

The RFQ snapshot deliberately contains only:

- request ID;
- provider-selection ID;
- exact service slug;
- exact area key;
- request scope summary;
- urgency;
- preparing operator; and
- creation timestamp.

It deliberately does not copy the customer name or raw customer message into the RFQ foundation record.

Every provider handoff is created with `status = prepared`. The database currently permits no other handoff state.

The provider-specific handoff ID is the intended future response-opportunity identity. However, RFQ preparation does not yet:

- contact a provider;
- mark a handoff delivered;
- assign a response deadline;
- create a `provider_response_opportunities` row; or
- start response-reliability timing.

Those actions belong to a separately authorized delivery slice. That delivery slice must re-check current provider eligibility immediately before contact; the immutable human selection snapshot is historical authority evidence, not a guarantee that a provider remains eligible later.

RFQ preparation writes `rfq_handoff_prepared` in the same transaction. Exact retries return the original RFQ and the original provider handoff IDs; they do not create duplicate handoffs or duplicate audit events.

An RFQ may be prepared only while the request is `ready` or `approved`. Once already prepared, an exact retry returns the immutable RFQ even if the request later moves to another status.

## RFQ delivery / response-opportunity activation

Delivery activation is intentionally split into two internal state transitions:

1. `prepared -> authorized`
2. `authorized -> delivered`

Authorization:

- requires operator `decide`;
- re-checks current provider eligibility for the RFQ's exact service and area;
- records `rfq_delivery_authorized`;
- performs no provider contact; and
- does not start response-reliability timing.

Delivery confirmation:

- requires prior authorization;
- requires an explicit timezone-aware response deadline;
- re-checks current provider eligibility again;
- records server-side delivery confirmation time;
- moves the handoff to `delivered`;
- creates exactly one `provider_response_opportunities` row using the durable handoff ID as `opportunity_id`;
- records `rfq_delivery_confirmed`; and
- starts response-reliability timing atomically with the delivery state transition.

Exact retries are idempotent. A retry with a different response deadline fails closed.

The service still performs no external email, WhatsApp, SMS or other provider send in this slice. A future authenticated delivery adapter must invoke the authorization gate before contact and confirm delivery immediately after successful send.

## Governed provider-response ingestion

Provider-response ingestion is software-only and applies only to an already delivered RFQ handoff.

The ingestion path:

- requires operator `decide`;
- accepts only structured `quote` or `decline` outcomes;
- requires an explicit timezone-aware provider response timestamp;
- binds the response to the delivered handoff and provider identity;
- writes immutable response evidence;
- writes `rfq_provider_response_recorded` in the same transaction;
- treats exact retries as idempotent; and
- fails closed when retry evidence conflicts.

It does not parse quotation documents, evaluate quote content, rank providers, contact providers, or dispatch work.

## Ranking readiness

`provider_ranking_readiness.assess_response_reliability_ranking_readiness(service_slug, area_key)` determines only whether a future response-reliability ranking implementation would have enough governed evidence.

Readiness requires:

- at least two currently eligible providers; and
- every currently eligible provider to have `sufficient_history` under the governed 90-day / minimum-5-completed-opportunities reliability metric.

If any current candidate has insufficient history, the entire candidate set remains unranked. The system does not silently rank only the providers with more data.

A ready result still states:

- `ranking_policy_enabled = false`;
- `ranked = false`; and
- `selected_provider_id = null`.

This readiness guard is the mandatory precondition for executable ranking.

## Deterministic response-reliability ranking

`provider_ranking.rank_providers_by_response_reliability(service_slug, area_key)` executes only after the readiness guard succeeds.

The ranking:

- orders providers by `response_reliability_bps`, highest first;
- uses no provider ID, creation order, model preference or hidden commercial factor;
- gives equal scores the same `rank_position`;
- does not treat presentation order within a tie as a tie-break;
- sets `requires_human_review = true` when any tie exists; and
- always returns `selected_provider_id = null`.

Provider selection remains human-only and is not modified by ranking.

## Normalized quote foundation

A normalized commercial quote may be recorded only after the corresponding RFQ handoff is delivered and a governed provider response of kind `quote` exists.

The normalized record captures deterministic structured fields only:

- `amount_minor`
- three-letter uppercase `currency`
- `scope_summary`
- `exclusions[]`
- `terms[]`
- optional `available_from`
- optional `estimated_duration_days`
- optional `validity_expires_at`

The record is immutable and idempotent. A conflicting retry fails closed.

Write access requires operator `decide`; retrieval requires `read`.

This slice performs no quotation-document parsing, model extraction, quote comparison, recommendation, provider selection, or award.

## Quote completeness validation

`quote_completeness.assess_quote_completeness(request_id, handoff_id)` evaluates one normalized quote using deterministic rules only.

Comparison readiness requires:

- a normalized price and currency;
- a non-empty scope summary;
- explicit exclusions disclosure; and
- explicit terms disclosure.

An expired quote is not comparison-ready and returns `needs_human_review`.

Missing availability date, estimated duration, or validity expiry are reported as informational gaps. They do not automatically fail every service because service-specific completeness policy has not yet been defined.

The result never evaluates commercial merit. It returns:

- `status = complete | incomplete | needs_human_review`;
- `comparison_ready`;
- exact missing required fields;
- informational gaps;
- blocking reasons;
- `evaluated = false`;
- `recommended = false`; and
- `selected = false`.

The read-only completeness endpoint requires operator `read`.

## Deterministic quote comparison

`quote_comparison.compare_request_quotes(request_id)` compares only normalized quotes from the same request that pass deterministic completeness validation.

The comparison:

- requires at least two comparison-ready quotes;
- compares price only when every ready quote uses the same currency;
- never performs currency conversion or fetches an exchange rate;
- identifies the lowest price factually when price is comparable;
- identifies the earliest available date only when every ready quote provides availability;
- identifies the shortest duration only when every ready quote provides duration;
- preserves scope, exclusions and terms as side-by-side evidence rather than scoring them; and
- reports any non-comparable dimension through `comparison_gaps`.

Quotes that fail completeness are excluded from the comparison result with their exact completeness status, missing required fields and blocking reasons.

The result always returns:

- `overall_winner_quote_id = null`;
- `recommended_quote_id = null`; and
- `selected_quote_id = null`.

The comparison endpoint is read-only and requires operator `read`.

## Human quote recommendation

A quote recommendation is an explicit human operator decision grounded in the current deterministic comparison set.

`POST /requests/{request_id}/quote-recommendation` requires operator `decide`. Retrieval requires `read`.

A recommendation:

- must reference a normalized quote in the current comparison-ready set;
- requires non-empty human rationale;
- snapshots deterministic comparison facts at decision time;
- is immutable and idempotent for an exact retry; and
- records `quote_recommendation_recorded` transactionally.

The record explicitly states:

- `recommendation_authority = human`;
- `award_created = false`; and
- `provider_contacted = false`.

Recommendation does not change request status, provider state, or RFQ state and does not constitute an award or dispatch instruction.

## Human quote award

A quote award is an explicit human commercial decision tied to the existing human recommendation.

`POST /requests/{request_id}/quote-award` requires operator `decide`. Retrieval requires `read`.

Before recording an award, the system:

- requires the referenced recommendation to belong to the request;
- verifies the recommended normalized quote still exists;
- re-checks that the quote is still comparison-ready;
- reconstructs current provider eligibility for the RFQ's exact service and area inside the award transaction; and
- rejects the award if the provider is no longer currently eligible.

The award is immutable and idempotent for an exact retry. Conflicting retries fail closed.

The award result explicitly states:

- `award_authority = human`;
- `provider_contacted = false`;
- `dispatch_created = false`; and
- `request_status_changed = false`.

This slice creates decision evidence only. Provider notification, dispatch and request-state transition remain separate future actions.

## Post-award delivery handoff

The post-award handoff is the first internal Phase 6 transition.

`POST /requests/{request_id}/delivery-handoff` requires operator `decide`. Retrieval requires `read`.

Activation requires an existing human quote award for the same request and snapshots the awarded commercial facts:

- provider ID;
- normalized quote ID;
- amount and currency;
- scope summary;
- exclusions and terms;
- optional availability date; and
- optional estimated duration.

The handoff and request-state transition are one transaction. The request moves from `ready` or `approved` to the existing `actioned` state and receives `actioned_at`.

The result explicitly states:

- `provider_contacted = false`;
- `dispatch_created = false`; and
- `appointment_created = false`.

No message, appointment, dispatch, or external side effect is performed in this slice.

## Delivery notification preparation

Post-award notification preparation creates exactly two durable records from the immutable delivery handoff:

- one customer notification with purpose `award_confirmation`; and
- one provider notification with purpose `award_notification`.

Message subject/body content is deterministic and derived only from persisted delivery facts such as price, currency and scope.

The current provider directory contains provider identity/display data but no governed delivery destination. Therefore this slice deliberately persists:

- `destination_channel = null`; and
- `destination_address = null`.

Customer delivery destination is also left unresolved rather than treating the inbound request source as outbound authority.

Preparation requires operator `decide`; retrieval requires `read`. Repeated preparation returns the same durable records and does not duplicate the audit event.

Every prepared notification explicitly reports:

- `status = prepared`;
- `sent = false`; and
- `external_action_performed = false`.

No email, WhatsApp, SMS or other outbound transport is invoked in this slice.

## Delivery appointment state

Appointment coordination is modeled independently from messaging transport.

An actioned request may have one durable appointment proposal with:

- a timezone-aware future start time;
- a timezone-aware end time after the start;
- the delivery handoff/provider identity;
- the proposing operator; and
- an explicit proposal reason.

The proposal is immutable. An exact retry returns the same proposal, while a different window or proposal evidence fails closed.

A separate confirmation transition records:

- the confirming operator;
- explicit confirmation reason; and
- confirmation timestamp.

Confirmation is also exact-retry idempotent and conflicting confirmation evidence fails closed.

Both proposal and confirmation require operator `decide`; retrieval requires `read`.

This state machine performs no external calendar booking and sends no notification. Those transports remain separate dependencies.

## Delivery execution status tracking

Delivery execution state is kept separate from the request workflow status.

A confirmed appointment may initialize exactly one durable delivery-status record in `scheduled` state. Initialization requires:

- the same request;
- the confirmed appointment;
- the persisted delivery handoff/provider identity;
- operator `decide`; and
- an explicit scheduling reason.

A separate human-controlled transition moves the record from `scheduled` to `in_progress` with an explicit start reason and timestamp.

Exact retries are idempotent. Conflicting scheduling or start evidence fails closed.

This slice deliberately excludes:

- completion;
- delays/exceptions;
- customer/provider notification delivery; and
- external calendar or dispatch operations.

## Delivery delay and exception recording

Operational exceptions are recorded as immutable evidence attached to the durable delivery-status record.

Supported kinds are deliberately limited to:

- `delay`;
- `service_issue`.

Each exception carries:

- caller-supplied UUID retry identity;
- the exact request/delivery/provider identity;
- timezone-aware occurrence timestamp;
- explicit human-authored summary;
- optional expected-resolution timestamp after occurrence; and
- recording operator.

A `delay` may be recorded while delivery is `scheduled` or `in_progress`. A `service_issue` requires `in_progress` delivery.

Exact retries with the same UUID/evidence are idempotent. Reusing an exception UUID with conflicting evidence fails closed.

This slice does not:

- resolve the exception;
- change request or delivery status;
- create a human-intervention queue item;
- send any notification; or
- perform any external action.

## Current exclusions

This routing stage does not yet include:

- automatic provider selection
- live RFQ delivery transport
- provider contact by this service
- fuzzy or proximity geography matching
- availability windows or capacity scoring
- model-controlled provider eligibility
- provider-state mutation

## Verification

Unit tests prove:

- `provider_routing` is registered without changing the existing default intake-analysis skill set;
- candidates are built only from the deterministic eligible-provider query;
- provider fields outside the routing contract are not exposed;
- an empty eligible set always escalates for human review;
- routing explanations use only deterministic candidate evidence;
- explanation output is explicitly unranked and unselected; and
- empty-result explanations do not invent failure reasons or broaden policy.

The PostgreSQL integration proof creates two otherwise matching providers, verifies that a non-compliant provider is excluded, and verifies that the surviving provider receives only the five deterministic eligibility explanations.

Ranking-policy unit tests prove that only governed response reliability is active, eligibility gates cannot become score factors, automatic selection and arbitrary tie-breaking are rejected, active weights total 100, and every enabled factor carries complete governance metadata.

The response-reliability PostgreSQL proof verifies a 90-day history window, exclusion of open opportunities, exclusion of stale history, on-time quote and decline handling, late/no-response handling, deterministic basis-point calculation, idempotent response recording, and fail-closed `insufficient_history` behavior below five completed opportunities.

The provider-selection PostgreSQL proof verifies current eligibility enforcement, immutable/idempotent human decisions, audit-event persistence, rejection of ineligible providers, request-state gating, and preservation of the original decision after later eligibility changes. Authorization tests prove that selection requires `decide` while retrieval requires only `read`.

The RFQ-handoff PostgreSQL proof verifies deterministic preparation from the immutable human selection, stable provider-specific handoff identities, privacy-minimized RFQ snapshots, one preparation audit event, idempotent retries after later request-state changes, required selection/state gates, and the critical negative guarantee that preparation creates no response-reliability opportunities. Authorization tests prove that preparation requires `decide` while retrieval requires only `read`.

The RFQ-delivery PostgreSQL proof verifies eligibility revalidation before authorization and again before confirmation, required transition order, one delivery audit event per transition, deterministic handoff-backed response-opportunity creation, idempotent confirmation, and fail-closed conflicting deadlines. Authorization tests prove both activation routes require `decide`.

The provider-response ingestion PostgreSQL proof verifies that only delivered handoffs accept quote/decline evidence, response timestamps cannot predate delivery, exact retries are idempotent, conflicting evidence fails closed, and the audit event is transactional.

The ranking-readiness PostgreSQL proof verifies that readiness is derived from the current deterministic eligible-provider set plus persisted response history and that one insufficient-history provider blocks the whole set. The same PostgreSQL proof now executes deterministic reliability ranking after readiness succeeds and verifies that no provider is automatically selected.


The normalized-quote PostgreSQL proof verifies that only delivered handoffs with a governed quote response can be normalized, exact retries are idempotent, conflicting normalized data fails closed, decline responses cannot become quotes, and one audit event is recorded transactionally.


The quote-completeness PostgreSQL proof verifies deterministic completeness against persisted normalized quote data, explicit missing-field reporting, comparison blocking for missing required disclosures, and preservation of the no-evaluation/no-recommendation/no-selection boundary.


The deterministic quote-comparison PostgreSQL proof verifies comparison across two governed, normalized, comparison-ready quotes from one request; same-currency price comparison; factual availability/duration comparisons; and preservation of the no-winner/no-recommendation/no-selection boundary.


The human quote-recommendation PostgreSQL proof verifies that recommendations are restricted to the current comparison-ready set, exact retries are idempotent, conflicting retries fail closed, one audit event is written, and recommendation creates neither an award nor provider contact.


The human quote-award PostgreSQL proof extends the recommendation flow through award, verifies that a newly non-compliant recommended provider blocks award until eligibility is restored, proves exact retry idempotency and conflicting retry rejection, and verifies one audit event with no provider contact, dispatch, or request-state mutation.


The post-award PostgreSQL proof extends the governed recommendation/award flow through delivery handoff, verifies the immutable award snapshot, atomic transition to `actioned`, exact retry idempotency, one audit event, and the absence of provider contact, dispatch and appointment creation.


The Phase 6 notification-preparation PostgreSQL proof extends the governed quote recommendation -> human award -> delivery handoff flow and verifies exactly one customer plus one provider notification, stable retry identities, unresolved destinations, one preparation audit event, and zero external sends.


The Phase 6 appointment PostgreSQL proof extends the governed flow through proposal and confirmation, verifies stable retry identity, persisted timestamps, exactly one proposal plus one confirmation audit event, and zero external calendar or messaging side effects.


The Phase 6 delivery-status PostgreSQL proof extends the governed flow through confirmed appointment, scheduled execution, and in-progress execution. It verifies stable retry identities, persisted start evidence, exactly one scheduling plus one in-progress audit event, and no completion/exception/notification side effects.


The Phase 6 delivery-exception PostgreSQL proof records both a delay and an in-progress service issue, verifies UUID-based exact retry idempotency, preserves chronological retrieval, writes one audit event per unique exception, and proves no resolution/intervention/notification side effects.
