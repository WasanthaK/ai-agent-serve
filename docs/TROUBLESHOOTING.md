# Troubleshooting Notes

These are issues encountered during the actual build.

## Broadcom hardware detected but no Wi-Fi interface

Seeing the BCM4360 in `lspci` does not prove a usable driver owns it. Check:

```bash
lspci -nnk
lsmod | grep wl
ip link
```

The working configuration used the Broadcom STA `wl` driver and blacklisted conflicting Broadcom modules.

## NetworkManager reports missing key-mgmt

Create the Wi-Fi profile explicitly and configure WPA-PSK instead of relying on automatic connection setup.

## Root filesystem much smaller than the SSD

Check LVM:

```bash
sudo vgs
sudo lvs
df -h /
```

The physical disk may be fully assigned to the volume group while the root logical volume uses only part of it.

## FastAPI container repeatedly restarts

Inspect:

```bash
docker ps -a
docker logs --tail 50 agent-server
```

A Python import or syntax failure can prevent Uvicorn from starting.

Before rebuilding:

```bash
python3 -m py_compile app.py
```

## NameError: app is not defined

This occurred when `app.py` was partially overwritten and a route decorator appeared before `app = FastAPI(...)`. Restore imports and application initialization before route definitions.

## IndentationError

Display numbered source lines:

```bash
nl -ba app.py | sed -n '160,185p'
```

Nano can also show line numbers:

```bash
nano -l app.py
```

## Changed .env but container still uses old values

`docker compose restart` restarts the existing container and may leave its original environment intact.

Recreate it:

```bash
docker compose up -d --force-recreate agent
```

## PostgreSQL password changed in .env but authentication fails

A PostgreSQL data volume is initialized with the original database credentials. Changing `POSTGRES_PASSWORD` later does not automatically change the existing database role password.

Update the role password in PostgreSQL so it matches the application environment.

## Special characters break DATABASE_URL

Embedding passwords containing characters such as `%` directly in a URL can trigger URL parsing/percent-encoding problems.

This project uses separate connection parameters instead:

```text
POSTGRES_HOST
POSTGRES_PORT
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
```

## Secrets displayed by docker compose config

Compose can expand environment values while rendering configuration. Avoid sharing command output that contains secrets.

If an API key is exposed, revoke it and issue a replacement.

## GitHub safety

Never commit:

- `.env`
- API keys
- database passwords
- private SSH keys
- customer data
- local backup files containing secrets

Keep `.env.example` in the repository with placeholders only.
