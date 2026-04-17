# Aperture Bridge — Dell G7 Deployment

The bridge is a small FastAPI service that runs 24/7 on the Dell G7. It
authenticates to Hik-Connect on your behalf, pulls fresh JPEGs from the
camera at Cul2vate, and exposes them to n8n via a bearer-token-protected
HTTPS endpoint fronted by Cloudflare Tunnel.

## Prereqs on the Dell

- Ubuntu/Debian (WSL2 on Windows is fine — we already do this for NSOS)
- `cloudflared` already installed and running (you have this for NSOS)
- Python 3.10+ (WSL Ubuntu 24.04 has 3.12)
- Outbound HTTPS to `*.ezvizlife.com` and `*.hik-connect.com` (no firewall
  changes needed on stock Eero)

## One-time install

1. **Pull the repo** on the Dell (if not already cloned):
   ```bash
   git clone https://github.com/Mika-Sibinkic/null-systems-business-framework.git ~/nsbf
   cd ~/nsbf/Active\ Projects/Branch\ Cam\ Testing/aperture/bridge
   ```

2. **Run the setup script** (it does everything — user, venv, systemd, env):
   ```bash
   sudo bash setup-dell.sh
   ```

   First run bails after creating a template env file. Edit it:
   ```bash
   sudo nano /etc/aperture-bridge.env
   ```
   Fill in:
   - `EZVIZ_ACCOUNT` — email from Hik-Connect step 1
   - `EZVIZ_PASSWORD` — password from Hik-Connect step 1
   - `CAMERA_SERIAL` — 9-digit serial
   - `BRIDGE_TOKEN` — generate with `openssl rand -hex 32`

   Re-run:
   ```bash
   sudo bash setup-dell.sh
   ```

   Service should now be running. Verify:
   ```bash
   systemctl status aperture-bridge
   journalctl -u aperture-bridge -n 50
   ```

3. **Local smoke test**:
   ```bash
   source /etc/aperture-bridge.env
   curl -s -H "Authorization: Bearer $BRIDGE_TOKEN" \
     http://localhost:8002/snapshot -o /tmp/snap.jpg
   file /tmp/snap.jpg   # should say: JPEG image data
   ls -lh /tmp/snap.jpg # ~100-400 KB typical
   ```

4. **Route via Cloudflare Tunnel**. Add to `/etc/cloudflared/config.yml`
   (snippet in `bridge/cloudflared-route.yml`), then:
   ```bash
   cloudflared tunnel route dns <YOUR_TUNNEL_NAME> aperture-bridge.<your-domain>
   sudo systemctl restart cloudflared
   ```

5. **Remote smoke test** — from your Mac:
   ```bash
   curl -s -H "Authorization: Bearer $BRIDGE_TOKEN" \
     https://aperture-bridge.<your-domain>/snapshot -o /tmp/snap.jpg
   open /tmp/snap.jpg      # should show live dock view
   ```

6. **Wire into n8n** — in the n8n Cloud UI, Settings → Variables:
   - `HIKVISION_CAMERA_URL` = `https://aperture-bridge.<your-domain>/snapshot`
   - `BRIDGE_TOKEN`         = same value as `/etc/aperture-bridge.env`

## Operations

### Health monitoring

The bridge has a `/healthz` endpoint. Add it to your uptime monitor (Better
Stack, Uptime Kuma, whatever NSOS already uses). Expected: 200 OK with
`{"status": "ok", ...}`. Alerts if 503.

### Logs

```bash
journalctl -u aperture-bridge -f          # tail live
journalctl -u aperture-bridge --since "1 hour ago"
```

### Restart

```bash
sudo systemctl restart aperture-bridge
```

### Updating the bridge code

```bash
cd ~/nsbf && git pull
cd Active\ Projects/Branch\ Cam\ Testing/aperture/bridge
sudo bash setup-dell.sh         # re-runs idempotently, restarts service
```

### Rotating the bridge token

1. Generate new: `openssl rand -hex 32`
2. Update `/etc/aperture-bridge.env`: `BRIDGE_TOKEN=<new>`
3. `sudo systemctl restart aperture-bridge`
4. Update n8n variable `BRIDGE_TOKEN` to match
5. Save + republish the n8n workflow

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| 401 on `/snapshot` | Bearer mismatch | Compare `$BRIDGE_TOKEN` in n8n and `/etc/aperture-bridge.env` |
| 503 "camera unreachable" | Hik-Connect offline | Check camera Platform Access Register Status; restart camera; check Cul2vate internet |
| 503 "pyezviz error: login failed" | EZVIZ credentials changed | Log into hik-connect.com with the saved creds; if broken, reset password, update env, restart |
| Service keeps restarting | Bad env file | `journalctl -u aperture-bridge -n 20` — missing var? |
| Snapshots returning but 3+ minutes stale | pyezviz session expired but error was masked | `sudo systemctl restart aperture-bridge` (auto-recovery in code should handle this — file a bug if you see it twice) |
| Snapshot returns but low resolution | Hik-Connect relay downsamples on low-bandwidth clients | Fix camera Video/Audio → Main Stream → resolution + bitrate if needed |
