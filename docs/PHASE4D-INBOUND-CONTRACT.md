# Phase 4D channel-neutral inbound contract

## Purpose

Phase 4D introduces a normalized inbound-message contract so website, email, WhatsApp and later channel adapters can feed the same downstream workflow.

The common rule is that an authenticated/verified customer message is normalized and stored durably before downstream AI processing. The normalized payload is data only; it never grants authority.

## Trust boundary

Channel adapters are responsible for authentication, signature validation, provider-specific parsing and source binding.

The normalized message is created only after those adapter checks succeed.

The normalized payload must not be treated as proof that a sender or channel is trusted. In particular, a raw external payload must never be allowed to choose its own authorized source merely by setting a field.

For the website adapter, `require_inbound_key` remains the authority boundary. The legacy request-body `source` field is checked against that authenticated source before normalization.

For SendGrid email ingress, provider signature verification occurs before parsing and normalization.

For WhatsApp, the existing Quixo Azure messaging service remains the public Twilio webhook boundary. It forwards a provider-neutral WhatsApp envelope to the agent using a credential explicitly bound to the `whatsapp` channel. The Mac Mini does not replace the existing Twilio webhook.

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
- persisted request source, customer name and message retain their existing meanings
- response fields remain unchanged

After successful source authentication and source-match validation, deterministic adapter code constructs a `NormalizedInboundMessage`.

When a validated `Idempotency-Key` is supplied, the adapter stores only its SHA-256 hash as the normalized external message identity. The raw idempotency key is not written to `inbound_messages`.

The website flow then:

1. validates/reserves the existing webhook idempotency contract when a key is present;
2. stores the normalized inbound message in `inbound_messages` before model analysis;
3. performs the existing request analysis and request persistence;
4. links the inbound record to the resulting request;
5. completes the existing webhook idempotency reservation.

Exact keyed retries reuse the same normalized inbound record. A completed retry can backfill/link the durable inbound record without repeating the model call. Unkeyed website deliveries are still accepted, but because the external sender supplied no delivery identity they cannot be deduplicated across separate HTTP deliveries.

No website sender identifiers or attachments are invented because the legacy webhook does not carry them.

## Email adapter

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

The verified SendGrid ingress checks provider authenticity before parsing, persists the normalized envelope before AI analysis and uses deterministic request identity for retry recovery.

Live DNS/MX/public webhook enablement remains deliberately deferred until explicitly authorized immediately before those external changes.

## WhatsApp adapter

`WhatsAppInboundEnvelope` is provider-neutral and preserves:

- sender external identifier
- optional sender phone/address
- optional display name
- text body
- required external message identifier
- optional conversation identifier
- optional timestamp
- bounded attachment references

The trusted agent route is `POST /webhook/whatsapp/inbound`.

The route requires the existing channel-bound credential for `whatsapp`, stores the normalized envelope before AI analysis, reuses the durable inbound UUID as the internal request UUID, and links retries idempotently.

The production topology is:

```text
WhatsApp -> Twilio -> existing Quixo Azure messaging service
         -> authenticated Agent ingress -> inbound_messages
         -> existing analysis/workflow
```

Twilio sender/webhook reconfiguration and live end-to-end external proof remain deliberately deferred until explicitly authorized.

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

Linking an inbound record to an internal request is deterministic: linking the same record to the same request is idempotent, while an attempt to relink it to a different request fails closed.

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

## Phase 4D completion boundary

The software path for the initial website, email and WhatsApp adapters is complete once the website durability slice is CI-verified and merged.

Live SendGrid and Twilio/Quixo external end-to-end enablement remains a separately authorized operational proof. No DNS, MX, public endpoint, Twilio sender/webhook or Azure messaging configuration should be changed without explicit authorization immediately before that action.
