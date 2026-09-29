---
choice: iPad on-tap LAN pull of the mounted Hikvision (Scriptable digest client)
tier: 2
date: 2026-07-22
status: accepted
alternatives_considered:
  - name: $75 always-on LAN mini-PC / Pi running mac_bridge.py
    reject_reason: Needs new hardware + an on-site drop; Mika wants no added hardware and it up ASAP. Kept as the fallback if the iPad pull fails on-site.
  - name: iPad's own camera (volunteer photographs the donation)
    reject_reason: Abandons the installed board+camera+injector+wall run (large sunk cost) and changes the imaging device; Mika explicitly rejected shipping only the iPad camera.
  - name: Hik-Connect / EZVIZ cloud pull (pyezviz on the Dell)
    reject_reason: VERIFIED DEAD for this camera; pyezviz/pyezvizapi see an empty device list; hikconnect lib has no capture method.
  - name: Hik-Partner Pro OpenAPI (cloud capture-by-serial)
    reject_reason: Official + no hardware, but blocked on partner OpenAPI AK/SK credential approval (~days). Pursue in parallel as the eventual hands-off cloud path; not a "now".
  - name: Keep Mac bridge on the Cul2vate LAN
    reject_reason: Dies whenever the Mac leaves/sleeps (the original 2026-04-17 failure). Not durable.
corroborating_signals:
  - RFC 2617 HTTP Digest; script response verified against the canonical test vector (node test, 2026-07-22)
  - docs/methods/camera-connectivity.md (Hik-Connect cloud-pull proven dead; ISAPI-on-LAN is the only method that ever pulled a frame)
  - iOS background-execution limits (apps suspended; no persistent inbound server), hence tap-time foreground pull, not a server
  - Existing working pipeline shape (2026-04-17 demo): iPad tap -> relay -> n8n -> frame -> vision -> Sheet
confidence:
  primary_claim: LIKELY        # digest auth math VERIFIED; on-device Scriptable HTTP-to-LAN + Keychain unverified until on-site
  cost_estimate: VERIFIED      # $0, uses hardware already installed + a free app
verification_probe: |
  On the Cul2vate LAN with the iPad: run camera-access/ipad/aperture-pull.js in
  Scriptable. Expect a 401->digest->200 JPEG from <camera-ip>, a POST to
  /api/donate, and a weight+item back. Off-LAN reproduction of the auth math:
  `node -e` require the script and check md5/buildDigestAuth vs the RFC vector
  (6629fae49393a05397450978507c4ef1); passes.
rollback:
  commit_sha: bd519cf
  steps:
    - Revert app/api/donate/route.ts image_b64 passthrough (git revert of this change set)
    - Leave the mounted-camera path unused; fall back to the $75 LAN mini-PC (camera-access/README.md Option A)
    - n8n vision node: revert base URL from NIM back to prior OpenAI credential if changed
superseded_by:
---

## Context

The mounted Hikvision at the Cul2vate dock is LAN-only; Hik-Connect cloud-pull is
verified dead for this camera; Mika is off-site with nothing on the Cul2vate LAN,
but wants the mounted camera (not the iPad's own camera, not new hardware) live
ASAP, the way the 2026-04-17 on-site demo worked. The iPad is already on that LAN
and is already the button-press front end.

## Decision

Use the on-site iPad as the camera relay **at tap time** (not as a background
server, which iOS forbids). A Scriptable script does an HTTP Digest GET of the
ISAPI snapshot from `<camera-ip>`, base64-encodes it, and POSTs it to the
existing Vercel relay `/api/donate` (extended with an `image_b64` passthrough);
n8n uses that frame with NVIDIA NIM vision and writes the Google Sheet. No Mac,
no LAN box, no Hik-Connect cloud. The digest client is verified against RFC 2617.

## Consequences

- Easier: mounted camera goes live with zero new hardware; survives the Mac
  leaving; the installed board/camera/injector investment is used as intended.
- Harder / committed to: the home-screen "app" becomes a Shortcut/Scriptable
  icon instead of a pure PWA URL; setup requires ~10 min on the iPad on-site
  (can't be done remotely). Credentials live in the iOS Keychain per device.
- Open risk (drops confidence to LIKELY until an on-site tap): Scriptable
  reaching the camera over plain HTTP on this network, and Keychain/UITable
  behavior; all standard, but unverified on this exact device/network. Fallback
  is the low-cost LAN box; the pipeline (relay + n8n + NIM) is identical either way.
