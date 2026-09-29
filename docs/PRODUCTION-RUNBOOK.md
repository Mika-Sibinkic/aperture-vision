# Aperture: production runbook

Full end-to-end launch checklist. Each section is ordered. Don't skip ahead.

## Architecture (at a glance)

```
   iPad PWA  (kiosk in Cul2vate kitchen)
       │
       ▼  HTTPS POST /api/donate
   Vercel serverless relay
       │
       ▼  HTTPS POST <n8n webhook>  + X-Aperture-Token
   n8n Cloud workflow
       │  1. verify token
       │  2. fetch bias table (Vercel /bias-table.json)
       │  3. fetch snapshot ──────► Dell G7 /snapshot ─► Hik-Connect ─► Camera (Cul2vate)
       │  4. gpt-4o vision call
       │  5. parse JSON, apply bias, apply tare subtraction
       │  6. write Google Sheet  (running log)
       │  7. write Farmbrite     (if configured)
       └─► HTTP 200 back to iPad
```

## Pre-launch checklist

### 0. Camera on-site (done)
- [x] Camera powered (orange PoE LED)
- [x] Static IP <camera-ip> on Cul2vate LAN
- [x] Zoom + focus locked; ChArUco + 6×6 yellow zone both sharp
- [x] Focus mode = MANUAL (won't drift)

### 1. Camera cloud relay (`docs/HIK-CONNECT-SETUP.md`)
- [ ] Hik-Connect account created (`aperture@example.com` or equivalent)
- [ ] Platform Access enabled on camera, Register Status = Online
- [ ] Camera added to Hik-Connect account via serial + verification code
- [ ] Serial number recorded for bridge env
- [ ] Firmware version recorded in `docs/FIRMWARE-FROZEN.md`
- [ ] Auto-upgrade confirmed OFF

### 2. Dell G7 bridge (`docs/BRIDGE-DEPLOY.md`)
- [ ] `setup-dell.sh` run, service active
- [ ] `/etc/aperture-bridge.env` filled in
- [ ] Local curl to `localhost:8002/snapshot` returns valid JPEG
- [ ] Cloudflare Tunnel route `aperture-bridge.<domain>` added
- [ ] Remote curl from Mac returns valid JPEG
- [ ] Healthz monitor configured

### 3. Third-party integrations
- [ ] Farmbrite API key (see §3a below)
- [ ] Farmbrite Inventory Type ID = <auto-created "Aperture Donations">
- [ ] Farmbrite Location ID for Ellington Ag Center
- [ ] Google Sheet created with headers (see §3b below)
- [ ] Google Sheet ID saved for n8n
- [ ] OpenAI API key (or Anthropic, or NIM Llama 3.2 Vision)

#### 3a. Farmbrite
See `scripts/discover-farmbrite-endpoint.sh`; run it once the client contact provides an
admin API key and it auto-creates the "Aperture Donations" inventory type
and prints the IDs.

Until then: n8n workflow has a `Guard: Farmbrite configured` IF node that
gracefully skips Farmbrite logging when env vars are empty; the Google
Sheet still gets every record.

#### 3b. Google Sheet template
Create a new Sheet named "Aperture: Cul2vate Donations". Add a tab called
"Donations" with these columns in row 1 (exact headers, exact order):

```
triggered_at | location | description | item_type | inside_zone |
charuco_detected | weight_lbs | weight_lbs_raw | weight_lbs_low |
weight_lbs_high | bias_multiplier | confidence | known_failure_flags |
notes | prompt_version | model | container_type | tare_lbs
```

The last two columns (`container_type`, `tare_lbs`) are for the
deterministic tare-subtraction pipeline (see `docs/DETERMINISM.md`).

Copy the Sheet ID from the URL (`docs.google.com/spreadsheets/d/<THIS>/edit`).

### 4. n8n workflow
- [ ] Import `n8n/aperture-workflow.json` as an inactive workflow
- [ ] Settings → Variables: set HIKVISION_CAMERA_URL, BRIDGE_TOKEN,
      APERTURE_SHARED_TOKEN, VISION_MODEL_PROVIDER, OPENAI_API_KEY,
      FARMBRITE_API_BASE, FARMBRITE_API_KEY, FARMBRITE_INVENTORY_TYPE_ID,
      FARMBRITE_LOCATION_ID, APERTURE_LOG_SHEET_ID, BIAS_TABLE_URL
- [ ] Connect OpenAI credential in the "Call vision model" node
- [ ] Connect Google Sheets OAuth credential in the "Append Donation to Sheet" node
- [ ] Activate workflow
- [ ] Copy production webhook URL for Vercel env

### 5. Vercel app
- [ ] Environment vars set in Project Settings: `N8N_WEBHOOK_URL`,
      `APERTURE_SHARED_TOKEN`, `NEXT_PUBLIC_LOCATION_LABEL`, `BIAS_TABLE_URL`
- [ ] `vercel --prod` deploys successfully
- [ ] `curl -X POST <vercel>/api/donate -H "content-type: application/json" \
      -d '{"description":"smoke test","location":"Cul2vate"}'`
      returns a 200 with a payload from n8n

### 6. iPad kiosk (`docs/IPAD-SETUP.md`)
- [ ] Open Vercel URL in Safari on iPad
- [ ] Add to Home Screen → name: "Aperture"
- [ ] Settings → Display & Brightness → Auto-Lock → Never
- [ ] Settings → Accessibility → Guided Access → On
- [ ] Launch app from Home Screen, triple-click side button to enable Guided Access
- [ ] Verify: big button is pressable, description textarea works, button
      press returns the n8n response text on success

### 7. Live smoke tests: 3 donations
- [ ] Donation 1: small box of mixed produce inside the 6×6 zone.
      Verify Sheet row + Farmbrite inventory delta
- [ ] Donation 2: larger stack, partially outside zone.
      Verify `inside_zone=false`, error message back to iPad, no Sheet row
- [ ] Donation 3: normal donation, check confidence + weight range
- [ ] Check n8n execution history; all three visible with inputs + outputs

## Day-of-launch

When the client contact/Joshua walk up to use it the first time:
1. Show them the iPad on its mount
2. Walk through one donation end-to-end
3. Show them the Google Sheet that's being populated
4. Give them the URL to the Sheet (view-only or edit, their call)
5. Tell them: if something looks wrong, hit the blue **Sign Out** of Guided
   Access (triple-click, enter passcode), take a screenshot, text Mika

## What to do when it breaks (on-call runbook)

### "The button doesn't do anything"
1. iPad connected to WiFi? (check Settings → WiFi)
2. Open iPad Safari manually, hit `https://<vercel>/api/donate` (expect 405
   Method Not Allowed for GET; this proves Vercel is reachable)
3. Vercel logs (Vercel dashboard → Deployments → Function Logs)

### "Every donation says camera unreachable"
1. Hit `https://aperture-bridge.<domain>/healthz` from your phone. 200?
2. If 503: `ssh mika@dell-g7` → `journalctl -u aperture-bridge -n 100`
3. If bridge is fine but `fetch_pic_url` is throwing: check
   hik-connect.com login works. Camera Platform Access status still Online?

### "Weights are way off"
1. Check `docs/FIRMWARE-FROZEN.md`; firmware still matches? If no, roll back.
2. Look at the residuals log (`training-loop/residuals.jsonl`). Is the bias
   table stale?
3. Has the camera moved? (Zoom/focus/position locked and MANUAL, but someone
   could have physically hit it.) Compare a fresh snapshot vs the baseline.

### "Farmbrite isn't getting records but the Sheet is"
The workflow intentionally degrades gracefully when Farmbrite creds are
missing. Check `FARMBRITE_API_KEY` in n8n variables.

### "I need to pause logging entirely"
Deactivate the n8n workflow in the n8n Cloud UI. Button presses will return
a clean error to the iPad. Re-activate when ready.

## On-site kit (keep in Cul2vate's office)

- 1 spare Cat6 cable (10 ft)
- 1 spare POE splitter/injector
- Printed card with:
  - Wifi network name Cul2vate expects the iPad on
  - Mika's cell phone
  - Vercel URL + QR code linking to it (in case iPad home screen icon
    gets deleted)
