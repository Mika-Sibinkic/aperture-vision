---
choice: Run Aperture with no self-managed always-on server (no Dell G7, no VPS)
tier: 2
date: 2026-07-28
status: accepted
alternatives_considered:
  - name: Dell G7 (WSL2) hosting the bridge + a local VLM
    reject_reason: >
      It was only ever needed to relay the camera; the iPad now does that at tap time.
      Keeping it would add the single most failure-prone component back: an 8 GB laptop
      whose WSL gets ~3.7 GB (too small for qwen2.5vl:3b), reachable only through a
      cloudflared tunnel that has already died twice, on a machine that also runs NSOS.
      It cannot serve the camera anyway - it is not on the Cul2vate LAN.
  - name: $5-10/mo VPS running the bridge + vision proxy
    reject_reason: >
      Costs money, needs patching/monitoring, and still cannot reach the LAN-only camera.
      It would only proxy the vision call, which NVIDIA NIM already does for free with
      better uptime than anything self-hosted.
  - name: $75 always-on mini-PC on the Cul2vate LAN
    reject_reason: >
      Genuinely solves hands-off capture and stays the fallback, but needs hardware plus
      an on-site install, and it introduces a box at a site with no IT support. Not needed
      while the iPad is present for every donation. Revisit if unattended capture is wanted.
  - name: Self-hosted n8n instead of n8n Cloud
    reject_reason: Trades a managed always-on service for a box we must keep alive. No benefit here.
corroborating_signals:
  - Live end-to-end run 2026-07-28 through Vercel prod -> n8n Cloud -> NIM -> Google Sheet, HTTP 200 in 11.5s
  - scripts/vision-regression-test.py --e2e - both controls pass against production
  - docs/methods/camera-connectivity.md - Hik-Connect cloud pull verified dead; ISAPI-on-LAN is the only capture path
  - Prior outages both traced to self-managed pieces (Mac bridge died 2026-04-17; cloudflared quick tunnels went NXDOMAIN)
confidence:
  primary_claim: VERIFIED      # full chain exercised against production, twice, both controls
  cost_estimate: VERIFIED      # $0 additional: Vercel + n8n Cloud existing plans, NIM free credits
verification_probe: |
  python3 scripts/vision-regression-test.py --e2e
  Expect: negative control -> empty/0 lb, positive control -> goods + a computed weight,
  "ALL CONTROLS PASSED". Any component being down surfaces here without touching the site.
rollback:
  commit_sha: 0bfd10a
  steps:
    - python3 scripts/rewire-n8n-ipad-nim.py --restore n8n/backups/<timestamp>.json
    - Redeploy the previous Vercel production deployment from the dashboard (instant rollback)
    - The camera, board, and iPad are untouched by this decision; nothing physical to undo
superseded_by:
---

## Context

Mika asked what should host Aperture always-on for production: the Dell G7, a VPS,
or something else. Every prior outage at Cul2vate came from a self-managed piece —
the Mac bridge died when the Mac left the site, and the cloudflared quick tunnels
went NXDOMAIN. The Dell was in the plan only because the camera needed a relay.

Once the iPad does the camera pull at tap time, that requirement disappears, and
with it the last reason to run a server at all.

## Decision

**Run no self-managed server.** Every always-on component is a managed service, and
the one on-premise step happens on a device that is already there and already in the
volunteer's hand:

| Piece | Where it runs | Always-on |
|---|---|---|
| PWA + `/api/donate` relay | Vercel (serverless) | managed |
| Orchestration, tare/bias, logging | n8n Cloud | managed |
| Vision (`llama-3.2-90b-vision-instruct`) | NVIDIA NIM | managed |
| Donation log | Google Sheets | managed |
| Camera capture | iPad, foreground, at the tap | on-site, on the LAN |

Nothing to keep running, nothing to restart, no tunnel, no systemd unit, no box that
can be off when someone walks up to donate.

## Consequences

- **Easier:** there is no server to be down. Recovery from a site power cut is "tap it
  again". The Dell stays dedicated to NSOS and is never a Cul2vate dependency.
- **Harder / committed to:** capture requires the iPad to be present and on the Cul2vate
  Wi-Fi, so unattended/hands-off capture is out until the low-cost LAN box is added. Vision
  depends on NIM's free credits — if they run dry, swapping providers is a single n8n
  credential edit (any OpenAI-compatible vision endpoint), not an architecture change.
- **Watch:** n8n Cloud plan execution limits, and Google Sheets OAuth token refresh in
  n8n — the two managed-service dependencies that can expire quietly. Both surface via
  the `--e2e` regression probe above, runnable from anywhere without visiting the site.
