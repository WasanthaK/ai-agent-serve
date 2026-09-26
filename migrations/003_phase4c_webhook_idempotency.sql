BEGIN;

CREATE TABLE IF NOT EXISTS webhook_idempotency (
    source TEXT NOT NULL,
    idempotency_key_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    request_id UUID NOT NULL,
    state TEXT NOT NULL DEFAULT 'processing'
        CHECK (state IN ('processing', 'completed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source, idempotency_key_hash)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_idempotency_request_id
    ON webhook_idempotency(request_id);

COMMIT;
