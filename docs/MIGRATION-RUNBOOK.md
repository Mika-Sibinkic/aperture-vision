# Aperture: Mac-bridge → Dell-G7 migration runbook

**Goal:** retire the Mac-hosted interim bridge + socat IPv6 link-local hack, move
the production path onto the always-on Dell G7 via Hik-Connect's cloud relay.
No on-site compute at Cul2vate, no Mac dependency, no tunnel rotation.

**Target state (after migration):**

```
iPad (Cul2vate)
  └─▶ https://<vercel-app-host>/api/donate
         └─▶ https://<n8n-host>/webhook/aperture-donate
                └─▶ https://bridge.example.com/snapshot_with_scale
                       └─▶ Dell G7 (Nashville, via Cloudflare Tunnel nsos-server)
                              └─▶ Hikvision cloud (Hik-Connect)
                                     └─▶ Camera at Cul2vate (outbound HTTPS only)
```

---

## Preflight: collect before you start

| Value | Source | Status |
|---|---|---|
| `EZVIZ_ACCOUNT` | Hik-Connect account email (create new if needed) | do during Phase 1 |
| `EZVIZ_PASSWORD` | Hik-Connect account password | do during Phase 1 |
| `CAMERA_SERIAL` | 9 digits, from camera body sticker OR retail box side panel OR purchase receipt | the client contact hunting |
| `BRIDGE_TOKEN` | Reuse `REDACTED-see-SECRETS.local.md` (already wired into n8n) | yes |
| Cloudflare tunnel | `nsos-server` UUID `<cloudflare-tunnel-id>`, already live on Dell | yes |
| Domain | `example.com`, already in Cloudflare DNS | yes |

---

## Phase 1: camera Platform Access (10 min, remote via still-live Mac socat if possible, otherwise on-site)

Follow `docs/HIK-CONNECT-SETUP.md` §1-§4. Summary:

1. **Create dedicated Hik-Connect account** at https://www.hik-connect.com.
   Save to 1Password.
2. In the camera UI:
   - Configuration → Network → Advanced → **Platform Access**
   - Platform Access Mode: `Hik-Connect`
   - Enable: ✓ , Stream Encryption: ✓
   - Verification Code: set a 6-12 char alnum, save it
   - Save, wait 30-60s, refresh; Register Status must read `Online`.
3. Bind camera to account: hik-connect.com → + Add Device → paste
   9-digit serial + verification code → confirm camera appears with live
   preview thumbnail.

**Blockers to watch for:**

- If Register Status stays `Offline` → DNS check: Network → Basic Settings → DNS should be `8.8.8.8` (set during static-IP migration).
- If the camera's UI isn't reachable now (Mac moved off Cul2vate LAN), Phase 1 requires an on-site visit. Deploy Phase 2 first, come back to Phase 1.

---

## Phase 2: deploy bridge on Dell G7 (30 min)

RustDesk into the Dell. All commands run in WSL Ubuntu (same env as NSOS).

```bash
# 1. Pull latest repo
cd ~  # or wherever you cloned business-framework
# replace with your actual clone path if different:
REPO=~/business-framework
[ -d "$REPO" ] || git clone https://github.com/<your-gh>/business-framework.git "$REPO"
cd "$REPO"
git pull

# 2. Run the idempotent installer (will bail on first run so you can edit the env)
cd "Active Projects/Branch Cam Testing/aperture/bridge"
sudo bash setup-dell.sh
```

First run will stop with:

```
EDIT THIS FILE NOW:  sudo nano /etc/aperture-bridge.env
```

Fill in the env file:

```
EZVIZ_ACCOUNT=<from Phase 1>
EZVIZ_PASSWORD=<from Phase 1>
EZVIZ_REGION=apiius.ezvizlife.com
CAMERA_SERIAL=<the 9 digits>
BRIDGE_TOKEN=REDACTED-see-SECRETS.local.md
SNAPSHOT_TTL_S=0.5
LISTEN_PORT=8002
```

Then:

```bash
sudo chmod 600 /etc/aperture-bridge.env
sudo bash setup-dell.sh       # second run completes the install + starts service
systemctl status aperture-bridge   # should be active (running)

# Local smoke test
source /etc/aperture-bridge.env
curl -s -H "Authorization: Bearer $BRIDGE_TOKEN" \
  http://localhost:8002/healthz
# expect:  {"status":"ok","camera_serial":"XXXX***"}

curl -s -H "Authorization: Bearer $BRIDGE_TOKEN" \
  http://localhost:8002/snapshot -o /tmp/snap.jpg
file /tmp/snap.jpg    # expect:  JPEG image data, ...
ls -lh /tmp/snap.jpg  # expect:  ~100-500 KB
```

If `/snapshot` fails with `camera unreachable via Hik-Connect`:
- Camera isn't registered yet (Phase 1 incomplete), OR
- Credentials mismatch in `/etc/aperture-bridge.env`, OR
- Camera went offline on Cul2vate's side

---

## Phase 3: wire Cloudflare Tunnel hostname (5 min)

Still on the Dell.

```bash
# 1. Edit the system-wide cloudflared config
sudo nano /etc/cloudflared/config.yml
```

Add this block to the `ingress:` list, **BEFORE** the catch-all `- service: http_status:404` line:

```yaml
  - hostname: bridge.example.com
    service: http://localhost:8002
    originRequest:
      connectTimeout: 10s
      noHappyEyeballs: true
```

Save. Then:

```bash
# 2. Register the DNS route (creates the CNAME in Cloudflare DNS automatically)
cloudflared tunnel route dns nsos-server bridge.example.com

# 3. Restart the tunnel so it picks up the new ingress
sudo systemctl restart cloudflared

# 4. Verify from the Dell
curl -s https://bridge.example.com/healthz
# expect: {"status":"ok","camera_serial":"XXXX***"}  OR  {"status":"degraded",...}

curl -s -H "Authorization: Bearer REDACTED-see-SECRETS.local.md" \
  https://bridge.example.com/snapshot_with_scale | python3 -m json.tool | head -20
# expect JSON with image_b64, image_bytes, scale_reading_lbs, etc.
```

From your Mac (different network):

```bash
curl -s -H "Authorization: Bearer REDACTED-see-SECRETS.local.md" \
  https://bridge.example.com/healthz
```

If this 200s from outside your home network, the tunnel is live.

---

## Phase 4: cut n8n over (≤1 min, via API)

**Do not do this manually.** Tell me "cut over" and I'll patch the workflow via the n8n API. For the record, the patch is:

```
Node: "Fetch snapshot + scale OCR (via Bridge)"
  url  FROM: https://<cloudflare-tunnel-host>/snapshot_with_scale
  url  TO:   https://bridge.example.com/snapshot_with_scale
  Authorization header: unchanged (same bearer)
```

Workflow stays active throughout; n8n doesn't require deactivation to
patch a single node via `PUT /workflows/{id}`.

Post-cutover verification (I'll run these automatically):

```bash
# Fire a donation through the full stack
curl -sS --max-time 60 -X POST https://<vercel-app-host>/api/donate \
  -H "content-type: application/json" \
  -d '{"description":"post-migration smoke","location":"Cul2vate","triggered_at":"…"}'
```

Expect `{"weight_lbs": 0 or <number>, "item_type": "empty" or <item>, ...}`
and a new row in the Donations tab of the Sheet.

---

## Phase 5: decommission Mac bridge + firmware freeze (10 min)

Already done by me at start of this session:

```bash
pkill -f "cloudflared tunnel"
pkill -f "mac_bridge.py"
pkill -f "socat.*TCP6"
pkill -f caffeinate
```

Camera firmware freeze: follow `docs/HIK-CONNECT-SETUP.md` §5:

1. Record current firmware version in `docs/FIRMWARE-FROZEN.md`
2. Disable auto-upgrade in camera UI (usually already off)
3. Disable Hik-Connect auto-update in the hik-connect.com dashboard if present
4. Take a snapshot-hash baseline with `sha256sum` so firmware-triggered
   JPEG-format changes can be detected later

---

## Rollback plan (if Phase 4 cutover breaks)

Tell me "rollback". I'll PUT the workflow back to the Mac-bridge URL via API.
For this to actually route successfully, you'd need to re-start the Mac bridge
(which means your Mac has to be back on Cul2vate's LAN). Unlikely scenario,
but the procedure is:

```bash
# On Mac, when back at Cul2vate:
cd "./bridge"
source .bridge-venv/bin/activate
python mac_bridge.py &
# in another terminal:
cloudflared tunnel --url http://localhost:8002
# use the random trycloudflare URL that prints, patch n8n via API with it
```

The cleaner rollback is just to re-run Phase 2 + 3 with corrected inputs.

---

## Ops reference (post-migration)

| Task | Command |
|---|---|
| Check bridge status | `systemctl status aperture-bridge` (on Dell) |
| Tail bridge logs | `journalctl -u aperture-bridge -f` |
| Restart bridge | `sudo systemctl restart aperture-bridge` |
| Rotate bridge token | Edit `/etc/aperture-bridge.env`, restart service, tell me to patch n8n |
| Rotate Hik-Connect creds | Same: edit env, restart |
| Update bridge code | `cd repo && git pull && cd …/bridge && sudo bash setup-dell.sh` (idempotent) |
| Tunnel health from anywhere | `curl https://bridge.example.com/healthz` |
| Camera offline | Check Register Status on hik-connect.com; usually self-recovers in 30s after power/net event |

Uptime monitoring: add `https://bridge.example.com/healthz` to
whatever NSOS already uses (Better Stack / Uptime Kuma). Alert on 503 for >2min.
