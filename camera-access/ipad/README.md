# Aperture — iPad as the on-tap camera bridge

> State: live · Optionality: high · Open to Change: yes. Goal: keep the **mounted
> Hikvision** as the imaging device (honors the installed board + camera + injector
> + wall run) with **no new hardware and no Mac** — the on-site iPad pulls the
> frame itself at the moment of the tap.

## Why this is the right unlock

- The mounted Hikvision is **LAN-only** (ISAPI digest over HTTP). Hik-Connect
  cloud-pull is dead for this camera (see `docs/methods/camera-connectivity.md`).
- The **iPad is already on the Cul2vate LAN** and is already the button-press
  front end. It is the one always-on-site device on the right network.
- iOS will **not** let an app run a persistent inbound server (apps get
  suspended), so the iPad can't be a box that n8n calls into. **It doesn't need
  to be.** The flow is volunteer-initiated: at the tap, the iPad is in the
  foreground and pulls the frame, then hands it up the pipeline. No background
  server required.
- A Shortcut/Scriptable network call is **not** bound by browser mixed-content
  or CORS rules (that's why the PWA `fetch()` couldn't do this, but this can).

## Flow

```
volunteer taps icon (Scriptable/Shortcut, foreground)
  └─ HTTP Digest GET http://<camera-ip>/ISAPI/Streaming/channels/101/picture  (LAN)
       └─ JPEG -> base64
            └─ POST https://<vercel-app-host>/api/donate  {image_b64, ...}
                 └─ n8n: image_b64 -> Vision (NIM) -> parse -> Google Sheet + Farmbrite
                      └─ weight + item returned -> shown on the iPad
```

No Mac. No LAN box. No Hik-Connect. The mounted camera stays the imaging device.

## Auth — verified

Hikvision ISAPI uses **HTTP Digest** (realm `IP Camera(<device-serial-short>)`). The digest
response construction in `aperture-pull.js` is **verified against the RFC 2617
test vector** (`node` test: MD5 primitives + full `6629fae4…` response + the
`IP Camera(<device-serial-short>)` realm parse all pass). If the camera is also configured to
allow **Basic** auth (Hikvision default is often `digest/basic`), a pure Apple
Shortcut works too — but the Scriptable digest path needs **no camera change**.

## ⭐ Follow `ONSITE-CARD.md` on site

`ONSITE-CARD.md` is the 4-step card to actually use on site: nothing to type, a
one-tap self-test that proves every hop, and a one-action fix list. The detail
below is background.

**Before leaving:** `python3 scripts/make-ipad-script.py` writes a pre-configured
`Aperture.local.js` (gitignored — it holds the camera password). AirDrop it to the
iPad. That removes every settings prompt from the on-site procedure.

## Backend status: LIVE and verified (2026-08-02)

Vercel prod relay → n8n (17 nodes, active) → NVIDIA NIM
`nvidia/nemotron-nano-12b-v2-vl`, prompt v0.6-net → Google Sheet + Farmbrite draft
order. A real POST returns 200 in 9.8–12.5 s and writes a row. Both regression controls pass:
`python3 scripts/vision-regression-test.py --e2e`. The **only** hop not yet exercised
is the iPad reaching the camera over the Cul2vate LAN — that is what the self-test checks.

## On-site install (~10 min, needs the iPad on Cul2vate WiFi) — background detail

1. **Install Scriptable** (free, App Store).
2. In Scriptable: **+** → paste the contents of `camera-access/ipad/aperture-pull.js`
   → name it **Aperture**. (Or AirDrop the file and import.)
3. **Run it once.** With the pre-configured build there is nothing to enter. (If you
   ever use the plain committed copy instead, it prompts once and stores in the iOS
   Keychain:)
   - Camera base URL: `http://<camera-ip>`
   - Username: `admin`
   - Password: see `SECRETS.local.md`
   - Snapshot path: `/ISAPI/Streaming/channels/101/picture`
   - Relay URL: `https://<vercel-app-host>/api/donate`
   - Location label: `Cul2vate, Ellington Ag Center`
   To re-run setup later: pass the argument `setup`, or delete the keys.
4. **Test tap:** put an item in the taped zone → run the script → confirm it
   shows `X.X lbs` + item. (Needs the n8n + relay companion changes below live.)
5. **Home-screen icon (make it "the app"):** either
   - Scriptable → script → **Add to Home Screen**, or
   - build a one-action **Apple Shortcut** ("Run Scriptable → Aperture"),
     add to Home Screen with a custom icon that matches the current PWA icon,
     and **Guided Access / Single-App Mode** so volunteers can't exit.

## Companion changes (server-side) — ALREADY DONE

Applied and deployed 2026-07-28 by `scripts/rewire-n8n-ipad-nim.py` (backs up →
verifies → PUTs → reads back; `--restore <backup>` rolls back):

1. **Relay** (`app/api/donate/route.ts`): accepts `image_b64`, `maxDuration` 120 s,
   legible error text. **Deployed to Vercel production.**
2. **n8n** workflow `<n8n-workflow-id>` (now 17 nodes, active):
   - Dead bridge-fetch node **deleted**; `Build vision request` reads the posted
     `image_b64` and assembles the NIM call (including the mandatory
     `response_format: json_object`).
   - `Vision: weight estimate` is now an HTTP request to NIM, authenticated by the
     n8n credential `NVIDIA NIM (Aperture)` so the key is never in the workflow JSON.
   - Parse node accepts NIM's `choices[0].message.content` and strips stray fences.

## Fallback

If on-site testing shows Scriptable can't reach the camera over HTTP on this
network (ATS/proxy edge cases) **and** the camera won't allow Basic auth, drop a
pre-flashed **$40–75 mini-PC / Pi** on the LAN running `bridge/mac_bridge.py`
(`camera-access/README.md` Option A). Same pipeline, box does the pull instead
of the iPad. This is the only path that needs hardware.

## Files

- `aperture-pull.js` — the Scriptable script (digest pull → POST → result UI).
  Contains no secrets; creds live in the iOS Keychain (set on first run) and in
  `SECRETS.local.md` for the installer.
