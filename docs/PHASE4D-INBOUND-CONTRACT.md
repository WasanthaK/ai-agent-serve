# Phase 4D channel-neutral inbound contract

## Purpose

Phase 4D introduces a normalized inbound-message contract so website, email, WhatsApp and later channel adapters can feed the same downstream workflow.

This first slice defines the contract only. Existing routes and workflow behavior are unchanged.

## Trust boundary

Channel adapters are responsible for authentication, signature validation, provider-specific parsing and source binding.

The normalized message is created only after those adapter checks succeed.

The normalized payload must not be treated as proof that a sender or channel is trusted. In particular, a raw external payload must never be allowed to choose its own authorized source merely by setting a field.

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

## Deliberate exclusions

This initial contract does not include:

- arbitrary metadata dictionaries
- authentication claims
- operator permissions
- service-delivery reasoning
- model analysis results
- provider-specific webhook bodies

Those responsibilities remain outside the channel-neutral message model.

## Next Phase 4D step

The next bounded change should adapt the existing website webhook into this contract internally while preserving its public API, authentication, idempotency and workflow behavior.

After the website path proves the abstraction, email and WhatsApp adapters can be added against the same normalized contract.
