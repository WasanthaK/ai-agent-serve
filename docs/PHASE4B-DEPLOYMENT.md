# Phase 4B Mac Mini deployment checkpoint

## Observed baseline — 2026-09-26

- Host: the Linux mini PC running the existing Compose stack.
- `~/ai-agent-serve` and `~/agent-server` both resolve to commit `df7dbeb`.
- The running API reports version `3.2.0`; `agent-server` and
  `agent-postgres` are healthy.
- The current API publishes port 8000 on all host interfaces. The Phase 4B
  Compose change will bind it to loopback.

These checks do not establish which of the two checkouts owns the running
Compose project. Identify it before changing either directory:

```bash
docker inspect agent-server --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}'
docker inspect agent-server --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}'
```

Use that checkout for deployment and keep the other untouched.

## Preparation

1. Review and integrate `phase-4/api-security` into the chosen Git branch.
   Verify a clean tree and the expected commit before pulling on the host.
2. In the active checkout, keep the existing `.env` and database volume.
   Generate a unique inbound secret and at least one individually identified
   operator secret. Set `AGENT_INBOUND_SOURCE=website` and configure
   `AGENT_OPERATOR_CREDENTIALS` as documented in
   [Installation](INSTALLATION.md). Give the smoke-test operator all five
   permissions. Keep `.env` mode `600`; never share or commit credentials.
3. Confirm the Compose configuration parses without printing secret values:

   ```bash
   docker compose config --quiet
   ```

## Rollout and verification

Run these commands from the active checkout after the reviewed branch is
available there:

```bash
docker compose build agent
docker compose run --rm --no-deps -v "$PWD/tests:/app/tests:ro" agent python -m unittest discover -s tests -p 'test_*.py' -v
docker compose up -d
docker compose ps
curl -sS http://127.0.0.1:8000/
```

In the test shell, securely provide `AGENT_INBOUND_API_KEY` and
`AGENT_OPERATOR_API_KEY` (the latter is a smoke-client variable holding one
configured operator key). Run the live checks from the active checkout:

```bash
python3 tests/smoke_phase3.py
python3 tests/smoke_phase4.py
```

These checks create test requests and invoke the model. The Phase 4B health
response must report version `3.3.0`, distinguishing it from Phase 4A's
`3.2.0`.

From a separate computer, a private tunnel provides access to the loopback
port. Replace `USER@HOST` with the SSH login and host address:

```text
ssh -L 18000:127.0.0.1:8000 USER@HOST
```

Then open `http://127.0.0.1:18000/docs`. The website webhook must use a
separately configured private TLS ingress; the tunnel is for operator access.

## Recovery

Collect `docker compose ps` and `docker compose logs --tail=100 agent` from
the active checkout. Keep the PostgreSQL volume intact. If credential or
authorization checks fail, stop the new API with `docker compose stop agent`
while diagnosing it.

If restoring the Phase 4A commit is necessary, create a recovery branch at
`df7dbeb` in the active checkout. Before starting its old unauthenticated API,
change the Compose port mapping there to `127.0.0.1:8000:8000`, then rebuild
and verify locally. The security configuration has no database migrations;
the previous data remains compatible.
