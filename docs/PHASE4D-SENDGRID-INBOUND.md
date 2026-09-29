# Phase 4D SendGrid inbound email adapter

## Scope

This slice implements the first provider-specific Email adapter from the Phase 4D roadmap.

The local flow is:

1. receive the exact raw SendGrid Inbound Parse `multipart/form-data` body
2. verify the SendGrid ECDSA signature over `timestamp + raw body`
3. only after verification, parse multipart fields
4. translate the provider payload into `EmailInboundEnvelope`
5. normalize it to `NormalizedInboundMessage(channel="email")`
6. durably persist the normalized envelope before model analysis
7. execute the existing request-analysis workflow
8. link the durable inbound record to the internal request
9. return a 2xx accepted response

The adapter does not grant workflow authority. Existing deterministic workflow and human-review rules remain unchanged.

## Trust boundary

The SendGrid signature is the provider-authentication boundary.

The route reads the raw request bytes before multipart parsing because parsing or rewriting multipart data can invalidate signature verification. Missing or invalid signatures are rejected before persistence or model calls.

`SENDGRID_INBOUND_PUBLIC_KEY` contains the base64-encoded ECDSA public key returned by the SendGrid webhook security-policy API. It is not a SendGrid API credential.

If the verification public key is absent or malformed, the route returns 503 so delivery is not accepted as successfully processed.

## Provider translation

The adapter uses the default Inbound Parse payload format and maps:

- `from` to sender address/display name
- `subject` to email subject
- `text` to the preferred message body
- `html` to a text-only fallback when `text` is absent
- email `Message-ID` header to `external_message_id`
- `References` or `In-Reply-To` to the best available conversation reference
- email `Date` header to `occurred_at`
- `attachment-info` plus multipart file fields to bounded attachment references

If `Message-ID` is absent, the adapter creates a deterministic SHA-256-derived provider identity from the normalized provider fields so exact retries remain idempotent.

Attachment contents are not stored or interpreted in this slice. Only metadata/reference information enters the normalized envelope.

## Retry behavior

The normalized inbound record is stored before AI processing.

For messages with an external message identity, exact provider retries return the same durable inbound record; conflicting reuse of the same identity fails closed.

The inbound record UUID is reused as the deterministic internal request UUID. This lets a retry recover an already-created request without creating a duplicate request.

If model analysis fails, the route returns the existing 502 analysis failure response, which is a 5xx and can be retried by SendGrid.

## Request-size limit

SendGrid supports inbound messages up to 30 MB, but this service deliberately retains its existing configurable safety ceiling of 10 MiB.

`AGENT_MAX_REQUEST_BYTES` therefore applies to the SendGrid route as well. Messages larger than the configured application limit are rejected before parsing. Live deployment must choose an explicit value appropriate to the Mac Mini's memory budget and expected attachment policy.

This slice does not raise the global limit automatically.

## Deployment composition

The production image now runs `runtime:app`, which imports the established `app:app` and adds provider-specific routes. This keeps the existing request workflow untouched while making provider adapters explicit at runtime.

The Dockerfile also copies the Phase 4D inbound modules into the image; earlier Phase 4D code was present in the repository but was not included by the older Dockerfile copy list.

## Deliberately not performed

This code slice does not:

- create or change DNS/MX records
- configure a SendGrid Parse Setting
- create a SendGrid webhook security policy
- retrieve or provision SendGrid credentials
- expose the Mac Mini publicly
- create tunnels or port forwarding
- change firewall rules
- send test email through SendGrid

Those external changes require explicit authorization immediately before they are performed.
