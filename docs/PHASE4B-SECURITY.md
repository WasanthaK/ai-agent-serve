# Phase 4B security work slices

Each slice should be reviewed and tested before the next is merged. The
technical roadmap remains the source of the overall phase scope.

## 4B.1 — Separate API roles (implemented on `phase-4/api-security`)

- Require a distinct inbound key for `POST /webhook/quote-request`.
- Require authenticated operators for direct analysis, request reads, replies,
  decisions and tools.
- Keep health and the published catalogue public.
- Reject missing, short or identical keys at startup and reject invalid keys
  before invoking the model or database.
- Record the authenticated operator for decisions rather than a caller
  supplied actor string.
- Add route authorization tests and update the live smoke clients.

The inbound key is a shared credential for one trusted channel adapter.
Operators receive individual credentials in 4B.3.

## 4B.2 — Channel ownership (implemented on `phase-4/api-security`)

- Bind the inbound credential to `AGENT_INBOUND_SOURCE`; reject a spoofed
  `source` value before invoking the model or database.
- Allow the authenticated channel to reply through
  `POST /webhook/quote-request/{request_id}/reply` only when the stored request
  belongs to that source. A different or unknown request returns 404.
- Derive the saved message channel from the credential, not from an arbitrary
  body value. Retain the operator reply route for manually entered replies.
- Test source spoofing, cross-channel access and unknown request identifiers.

This single inbound credential is for one trusted channel adapter. Anyone
holding that credential can act on requests owned by that channel; individual
customers must not receive it. Additional channel adapters need distinct
credentials and source mappings before they are enabled.

## 4B.3 — Operator identity and decisions (implemented on `phase-4/api-security`)

- Configure individually identified operator keys and explicit permissions:
  `read`, `analyze`, `reply`, `decide` and `tools`.
- Record the authenticated identity in approval, rejection, tool and manual
  reply events, with the reply event saved atomically alongside its message.
- Deny a read-only operator's attempts to decide, execute tools, analyze or
  submit replies before touching the database or model.
- Revoke an operator by removing its credential and restarting the service;
  never use a body field as the authoritative actor.

## 4B.4 — Audit and secrets (implemented on `phase-4/api-security`)

- Log denied authentication and authorization with fixed reason codes, route
  templates, method and authenticated actor ID where available. The audit log
  does not inspect headers, URL values or request bodies.
- Return generic model and tool failure messages without exposing exception
  text. Store an error type in tool failure events rather than error text.
- Keep drafted customer messages in the protected API response, while the tool
  completion event records only the tool name. Request creation and reanalysis
  events record a count of missing fields, not their content.
- Preserve operator-entered approval/rejection reasons as intentional audit
  data visible through the protected request-events route. Operators should
  use these fields for decision rationale, not credentials.

Denial events go to the application log; they are not attached to a request
record because authentication can fail before a request ID is known. Log
retention follows the host's Docker logging configuration.

## 4B.5 — Rotation and deployment verification (code and guide prepared)

- Support up to two distinct inbound keys and two keys per operator during a
  controlled rotation. Remove the old key and restart to revoke it.
- Bind the Compose API port to loopback and document private SSH access. An
  external webhook requires a separately configured private ingress with TLS.
- Follow [the deployment guide](PHASE4B-DEPLOYMENT.md) to identify the active
  checkout, configure credentials, run the suite and both live smoke tests.

The live Mac Mini checks remain open until the branch is deployed. The
running Phase 4A service remains at version 3.2.0 meanwhile.

Request size, rate controls, idempotency and operational metrics belong to
Phase 4C in the technical roadmap.
