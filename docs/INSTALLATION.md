# Installation Guide

This guide documents the practical build path used to turn an older Intel Mac mini into a small Ubuntu AI agent server.

## 1. Install Ubuntu Server

Use the AMD64/x86-64 Ubuntu Server image for an Intel Mac. Boot the installer in EFI mode.

After installation:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt autoremove -y
sudo apt autoclean
sudo reboot
```

## 2. Broadcom BCM4360 Wi-Fi

Identify the adapter and active driver:

```bash
ip link
lspci -nn
lspci -nnk
```

For BCM4360 hardware, install the Broadcom STA driver:

```bash
sudo apt update
sudo apt install broadcom-sta-dkms
sudo modprobe wl
```

If a conflicting Broadcom module owns the device, create `/etc/modprobe.d/broadcom-wl.conf`:

```text
blacklist b43
blacklist bcma
blacklist brcmsmac
blacklist brcmfmac
blacklist ssb
```

Then:

```bash
sudo update-initramfs -u
sudo reboot
```

Verify that the kernel driver in use is `wl`.

## 3. Wi-Fi with NetworkManager

```bash
nmcli device
nmcli device wifi list
```

If automatic connection fails because key management is missing, explicitly create a WPA-PSK profile with NetworkManager.

## 4. SSH

```bash
sudo apt install openssh-server -y
sudo systemctl enable --now ssh
hostname -I
```

Prefer SSH key authentication for a headless server.

## 5. Check storage and LVM

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
sudo vgs
sudo lvs
df -h /
```

If the root logical volume does not use the available free extents:

```bash
sudo lvextend -l +100%FREE -r /dev/ubuntu-vg/ubuntu-lv
```

Verify device names before running storage commands.

## 6. Install Docker

Install Docker Engine, containerd, Buildx and the Compose plugin using Docker's official Ubuntu repository.

Verify:

```bash
docker version
docker compose version
docker ps
```

Configure Docker log rotation to prevent logs from consuming the disk.

## 7. Configure the application

Clone the repository and enter it:

```bash
git clone git@github.com:WasanthaK/ai-agent-serve.git
cd ai-agent-serve
```

Create the environment file:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Supply your own OpenAI API key and PostgreSQL password. Generate a distinct
key for the inbound website adapter and for each operator:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Set `AGENT_INBOUND_API_KEY` to the inbound value and
`AGENT_INBOUND_SOURCE=website`. Configure operators in
`AGENT_OPERATOR_CREDENTIALS` as a JSON array. For example, the following
shows the format in `.env`; replace each short placeholder with a different
generated key before starting the service:

```text
AGENT_OPERATOR_CREDENTIALS='[{"id":"primary","key":"<key-1>","permissions":["read","analyze","reply","decide","tools"]},{"id":"viewer","key":"<key-2>","permissions":["read"]}]'
```

The five permissions are `read` (request and history reads), `analyze`
(direct analysis), `reply` (manual reply ingestion), `decide` (approve/reject)
and `tools` (controlled tool execution). Give each person their own key and
only the permissions they need. Remove an operator entry and restart the
agent container to revoke access. The API refuses to start with missing,
short, duplicate or malformed keys or permissions. Never commit `.env`.

For a controlled key rotation, the server also accepts two inbound keys in
`AGENT_INBOUND_API_KEYS` (a JSON array) in place of the single
`AGENT_INBOUND_API_KEY`. An operator entry can use `"keys":["<old>","<new>"]`
in place of `"key":"<current>"`. Never configure both inbound variables
with values. Restart the agent after adding the new key, verify it, then
remove the old key and restart again. The API rejects duplicate keys and
more than two keys per identity.

## 8. Build and start

```bash
docker compose up -d --build
docker ps
```

Both the API and PostgreSQL containers should become healthy.
The API is bound to `127.0.0.1:8000` on the Mac Mini. From another computer,
open an SSH tunnel with `ssh -L 18000:127.0.0.1:8000 USER@HOST` (replace
`USER@HOST` with your SSH login and host address), then use
`http://127.0.0.1:18000/`. An external website webhook requires a
separately configured private TLS ingress before exposure.

## 9. Test

Health endpoint:

```bash
curl http://localhost:8000/
```

Quote-request webhook:

```bash
curl -X POST http://localhost:8000/webhook/quote-request \
  -H "X-API-Key: $AGENT_INBOUND_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"source":"website","customer_name":"Test Customer","message":"My kitchen tap is leaking badly and I need someone today."}'
```

A successful persisted request returns a UUID `request_id` along with the structured AI analysis.
Load your keys into the shell securely before using the examples and smoke tests.
The `.env` file used by Docker Compose is not automatically exported to the shell.
For the smoke tests, export `AGENT_OPERATOR_API_KEY` in the test shell as the
key of an operator with all five permissions. This shell variable is only a
smoke-client setting; the server reads `AGENT_OPERATOR_CREDENTIALS`.
For a customer reply received by the website adapter, use the inbound key with
`POST /webhook/quote-request/{request_id}/reply` and a JSON body containing
`message`. The request must belong to the configured inbound source. The
operator's key remains available for manually entered replies at
`POST /requests/{request_id}/reply`. Never give either key to a customer.

## 10. Verify PostgreSQL

```bash
docker exec -it agent-postgres psql -U agentuser -d agentdb
```

Then query recent requests:

```sql
SELECT id, source, customer_name, category, urgency,
       needs_human_review, status, created_at
FROM agent_requests
ORDER BY created_at DESC
LIMIT 5;
```
