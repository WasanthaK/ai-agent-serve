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

Supply your own OpenAI API key and PostgreSQL password. Never commit `.env`.

## 8. Build and start

```bash
docker compose up -d --build
docker ps
```

Both the API and PostgreSQL containers should become healthy.

## 9. Test

Health endpoint:

```bash
curl http://localhost:8000/
```

Quote-request webhook:

```bash
curl -X POST http://localhost:8000/webhook/quote-request \
  -H "Content-Type: application/json" \
  -d '{"source":"website","customer_name":"Test Customer","message":"My kitchen tap is leaking badly and I need someone today."}'
```

A successful persisted request returns a UUID `request_id` along with the structured AI analysis.

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
