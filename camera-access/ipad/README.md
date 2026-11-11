# iPad as the camera bridge

The mounted Hikvision stays the imaging device, with no new hardware and no Mac. The
iPad on the dock pulls the frame itself at the moment of the tap.

## Why the iPad pulls the frame

- The camera is LAN-only (ISAPI digest over HTTP). Hik-Connect cloud-pull did not work
  for this camera (CHANGELOG, 2026-07-22).
- The iPad is already on the Cul2vate LAN and is already the button.
- iOS suspends background apps, so the iPad cannot be a server that n8n calls into. It
  does not need to be. The volunteer starts each tap, so the iPad is in the foreground
  and pulls the frame then.
- A Scriptable request is not bound by browser mixed-content or CORS rules. That is
  why a web page's `fetch()` could not do this and Scriptable can.

## Flow

```
volunteer taps icon (Shortcut -> Scriptable, foreground)
  └─ HTTP Digest GET http://<camera-ip>/ISAPI/Streaming/channels/101/picture  (LAN)
       └─ JPEG -> base64
            └─ POST https://<vercel-app-host>/api/donate  {image_b64, ...}
                 └─ n8n: image_b64 -> Vision (NIM) -> parse -> Google Sheet + Farmbrite
                      └─ weight + item returned -> shown on the iPad
```

## Install

Follow `ONSITE-CARD.md`. It is the one install procedure.

`python3 scripts/make-ipad-script.py` writes a pre-configured `Aperture.local.js`
(gitignored; it holds the camera password), so nothing is typed on site. If you run
the plain committed `aperture-pull.js` instead, it asks once for each of these and
stores them in the iOS Keychain:

- Camera address: `http://<camera-ip>`
- Camera username: `admin`
- Camera password
- Snapshot path: `/ISAPI/Streaming/channels/101/picture`
- Relay URL: `https://<vercel-app-host>/api/donate`. Export and undo use the same host.
- Location label
- Device token: the value of `APERTURE_DEVICE_TOKEN` in Vercel. Leave it blank only
  while that variable is unset.

To run setup again, pick **Re-enter settings** from the in-app menu.

## Backend status (2026-08-02)

Vercel relay → n8n (17 nodes, active) → NVIDIA NIM `nvidia/nemotron-nano-12b-v2-vl`,
prompt v0.8-scene → Google Sheet + Farmbrite draft order. A real POST on prompt
v0.6-net returned 200 in 9.8-12.5 s and wrote a row (2026-08-02). The three regression
controls passed on v0.8-scene the same night, and the system check passed on the dock.
Run the system check again after any network change.

## Auth

Hikvision ISAPI uses HTTP Digest. The digest code in `aperture-pull.js` is checked
against the RFC 2617 test vector by `scripts/check-ipad-script.sh`. If the camera also
allows Basic auth, a plain Apple Shortcut could pull the frame too, but the Scriptable
digest path needs no camera change.

## Fallback

If Scriptable cannot reach the camera over HTTP on some network and the camera will
not allow Basic auth, put a small mini-PC or Pi on the LAN that pulls the frame and
posts it to the relay. This is the only path that needs hardware.
