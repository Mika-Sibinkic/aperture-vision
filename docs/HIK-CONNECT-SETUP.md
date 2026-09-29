# Hik-Connect setup + firmware freeze: camera side

One-time setup at the camera. ~10 minutes on-site. After this, the camera is
reachable from anywhere via Hikvision's free cloud relay (no port forwarding,
no Cul2vate LAN access needed).

## 1. Pick a dedicated Hik-Connect account

Do NOT reuse a personal account. Create one just for this camera.

- Open https://www.hik-connect.com/ in a browser
- Click **Register**
- Use an email you control; recommended: `aperture@example.com` (or create
  a Gmail like `aperture-service@example.com` if the Cul2vate domain isn't
  ready for a new mailbox)
- Choose a strong password (generate with `openssl rand -base64 24`)
- Verify the email, complete registration
- Save credentials in 1Password; this is now a production secret

## 2. Enable Platform Access on the camera

With the VLC + socat + curl setup you used for the install (Mac bridging
`localhost:8888` to the camera's IPv6 link-local), log into the web UI:

1. **Configuration → Network → Advanced Settings → Platform Access**
2. Set **Platform Access Mode** = `Hik-Connect`
3. Set **Enable** ✓
4. Set **Stream Encryption** ✓
5. Verification Code: set a 6-12 char code (letters + numbers, no spaces).
   Write it down; you'll need it next step. Treat as a secret.
6. Click **Save**
7. Refresh the page and confirm **Register Status** shows `Online`
   (may take 30-60 sec after saving; refresh a few times)

If Register Status stays `Offline`:
- Cul2vate's Eero is probably fine (camera makes outbound HTTPS to
  dev.hik-connect.com:443), but re-check Network → Basic Settings → DNS
  is `8.8.8.8` (we set this during the static-IP migration)
- If still failing, the camera needs a firmware that supports Hik-Connect.
  All 2020+ firmware does. Check **System → Maintenance → Firmware Version**;
  V5.5.0+ is fine.

## 3. Bind the camera to your Hik-Connect account

On https://www.hik-connect.com/ (logged into the account from step 1):

1. Click the **+** (Add Device) button
2. Serial number: enter the 9-digit serial from the camera label (or
   Configuration → System → System Settings → Basic Information → Serial No.)
3. Verification code: the one you just set in step 2.5
4. Device name: `Cul2vate Dock Cam`
5. Click **Add**

Camera should now show up in your dashboard with a live preview thumbnail.

## 4. Save the serial for the bridge config

You'll paste this into `/etc/aperture-bridge.env` on the Dell G7:

```
CAMERA_SERIAL=<the 9-digit serial>
EZVIZ_ACCOUNT=<the email from step 1>
EZVIZ_PASSWORD=<the password from step 1>
```

## 5. Firmware freeze (CRITICAL for production stability)

Hikvision does NOT push automatic firmware updates to cameras by default, but
the UI has an "Upgrade" button that's tempting to hit during troubleshooting.
Lock this down:

### 5a. Document the current firmware

```
Configuration → System → System Settings → Basic Information
  → Firmware Version:  V5.X.X build XXXXXX
  → Encoding Version:  V7.X build XXXXXX
```

Write both to `docs/FIRMWARE-FROZEN.md` in this repo so future-you knows what
was running when the system last worked.

### 5b. Disable auto-update + upgrade prompts

```
Configuration → System → Maintenance → Upgrade & Maintenance
  → Auto-upgrade:  OFF (should already be off by default)
```

Some firmware versions also have:
```
Configuration → System → System Settings → Menu → "Check for update on login"
  → OFF
```

### 5c. Lock down the Hik-Connect device firmware channel

On https://www.hik-connect.com → the camera → Settings → "Auto-Update":
- Turn OFF if present. Hik-Connect does NOT push firmware without user
  action, but the setting exists on some account tiers; disable to be safe.

### 5d. Block firmware-related outbound if truly paranoid

(OPTIONAL; don't do this for launch, only if you ever see firmware-related
regressions.) On the Eero, block outbound traffic from the camera's MAC to:
- `upgrade.hikvision.com`
- `firmware.hik-connect.com`

The camera will continue to work fine without these. Hik-Connect cloud relay
uses `*.ezvizlife.com` and `*.hik-connect.com`; DO NOT block those.

### 5e. Record the snapshot API fingerprint

Run this ONCE after setup to establish the baseline:

```bash
# From the Dell G7, after bridge is running:
curl -s -H "Authorization: Bearer $BRIDGE_TOKEN" \
  https://aperture-bridge.<your-domain>/snapshot \
  -o /tmp/baseline.jpg
sha256sum /tmp/baseline.jpg > docs/FIRMWARE-FROZEN.md.sha
file /tmp/baseline.jpg >> docs/FIRMWARE-FROZEN.md.sha
```

The hash will of course change every time (scene differs), but the `file`
output tells you the format. If a firmware update ever silently changes
resolution, the JPEG header size changes and you'll notice.

## 6. Regression check: can you fetch a snapshot without touching the LAN?

From a laptop on a DIFFERENT WiFi network (your phone's hotspot works), in
Python:

```python
from pyezviz import EzvizClient, EzvizCamera
c = EzvizClient("aperture@example.com", "<password>", "apiius.ezvizlife.com")
c.login()
cam = EzvizCamera(c, "<9-digit-serial>")
cam.load()
print(cam.fetch_pic_url())   # signed URL to a JPEG
```

Paste the URL in a browser. Should show the current dock view.

If this works → Hik-Connect is ready and your bridge will work from anywhere.
If it fails → check Platform Access → Register Status on the camera, and
re-verify the credentials.

## Recovery: what breaks this?

| Scenario | Fix |
|---|---|
| Power outage at Cul2vate | Camera auto-reconnects when power returns. Zero intervention. |
| Eero reboot / WAN IP change | Camera re-registers in ~30 sec. Zero intervention. |
| Hik-Connect password changed | Update `/etc/aperture-bridge.env` on Dell, `systemctl restart aperture-bridge`. |
| `pyezviz` library breaks after Hikvision API change | Pin to last-known-working version in `requirements.txt` (already done: `pyezviz==0.2.2.5`). If the pinned version stops working, check pyezviz GitHub releases for a patch. |
| Firmware auto-updated despite lockdown | Read `docs/FIRMWARE-FROZEN.md` for the last-known-working version. Roll back via System → Maintenance → Upgrade → select offline firmware file (download from hikvisionusa.com if needed). |
