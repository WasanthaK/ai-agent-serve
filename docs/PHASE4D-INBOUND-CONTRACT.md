# Phase 4D channel-neutral inbound contract

## Purpose

Phase 4D introduces a normalized inbound-message contract so website, email, WhatsApp and later channel adapters can feed the same downstream workflow.

The contract is proven on the existing website quote-request webhook while preserving that route's public request/response shape and its established authentication, source-binding, idempotency and workflow controls.

A provider-neutral email adapter contract is also defined. The current slice adds durable normalized-envelope persistence, but email ingress is still not live until a provider-specific verified route is implemented and proven.

## Trust boundary

Channel adapters are responsible for authentication, signature validation, provider-specific parsing and source binding.

The normalized message is created only after those adapter checks succeed.

The normalized payload must not be treated as proof that a sender or channel is trusted. In particular, a raw external payload must never be allowed to choose its own authorized source merely by setting a field.

For the website adapter, `require_inbound_key` remains the authority boundary. The legacy request-body `source` field is still checked against that authenticated source before normalization. The adapter receives the authenticated channel from deterministic application code; it does not trust the body to select a channel.

For future email ingress, provider-specific webhook authentication/signature validation must occur before constructing the provider-neutral email envelope. The email adapter itself only accepts a server-controlled authenticated channel and rejects non-email channels.

## Contract

`NormalizedInboundMessage` contains:

- `schema_version` — currently `1.0`
- `channel` — normalized adapter identifier such as `website`, `email` or `whatsapp`
- `text` — normalized human-readable message text
- `sender` — optional transport-neutral sender identifiers
- `external_message_id` — optional provider/channel message identifier
- `external_conversation_id` — optional provider/channel thread or conversation identifier
- `occurred_at` — optional channel event timestamp
- `linked_request_id` — optional known internal request UUID for replies/follow-ups
- `attachments` — optional bounded attachment references and metadata

Unknown fields are rejected.

## Sender

`InboundSender` can contain:

- `external_id` — provider-specific sender identifier
- `address` — channel address such as email address or phone number
- `display_name` — optional display name

These values are descriptive identifiers. They do not grant application authority.

## Attachments

Attachments are references only in this phase. The contract records:

- reference
- media type
- optional filename
- optional byte size

The normalized contract does not download, parse or trust attachment contents.

A message is limited to 20 attachment references.

## Website adapter

`POST /webhook/quote-request` keeps its existing external contract:

- body fields remain `source`, optional `customer_name`, and `message`
- inbound authentication remains unchanged
- body `source` must still match the authenticated configured channel
- `Idempotency-Key` handling remains unchanged
- idempotency identity remains authenticated source + customer name + message text
- persisted source, customer name and message retain their existing meanings
- response fields remain unchanged

After successful source authentication and source-match validation, deterministic adapter code constructs a `NormalizedInboundMessage` from the authenticated channel and message text. Downstream analysis, idempotency and persistence consume the normalized channel/text values.

No website sender identifiers or attachments are invented by the adapter because the legacy webhook does not carry them.

## Email adapter contract

`EmailInboundEnvelope` is the provider-neutral input to email normalization. It contains:

- sender address
- optional sender display name
- optional subject
- plain-text body
- required external message identifier
- optional external conversation/thread identifier
- optional occurrence timestamp
- bounded attachment references

The adapter converts this envelope into `NormalizedInboundMessage` with channel `email`.

If a subject is present, normalized text is constructed as:

```text
Subject: <subject>

<body>
```

The adapter preserves sender identity, external message/thread identifiers, occurrence time and attachment references in the normalized message.

The adapter does not authenticate SendGrid, Gmail, Microsoft Graph or any other provider webhook. Provider-specific verification remains outside this contract.

## Durable inbound-envelope persistence

Normalized inbound messages are stored in `inbound_messages` before downstream AI processing.

The durable record preserves:

- schema version
- authenticated channel
- normalized message text
- sender envelope
- external message identifier
- external conversation identifier
- occurrence timestamp
- attachment references
- optional linked internal request ID
- correlation ID
- deterministic payload hash

For messages with an `external_message_id`, `(channel, external_message_id)` is unique.

An exact retry of the same normalized envelope returns the existing stored record. Reuse of the same external message identity with different normalized content fails closed as a conflict.

Linking an inbound record to an internal request is also deterministic: linking the same record to the same request is idempotent, while an attempt to relink it to a different request fails closed.

This storage layer does not itself invoke a model, choose workflow authority or trust provider input. It only persists a normalized message that has already crossed the channel-authentication boundary.

## Deliberate exclusions

The normalized contract does not include:

- arbitrary metadata dictionaries
- authentication claims
- operator permissions
- service-delivery reasoning
- model analysis results
- provider-specific webhook bodies

Those responsibilities remain outside the channel-neutral message model.

## Next Phase 4D step

After this persistence slice is merged and PostgreSQL integration-tested, implement the first provider-specific verified email ingress. SendGrid is the preferred first provider: verify its inbound signature before parsing/normalization, persist the normalized envelope before AI analysis, and keep delivery retry-safe. Do not configure public DNS, MX records or external webhook delivery until the route is implemented and explicitly authorized for live setup.
