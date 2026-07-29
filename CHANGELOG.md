# Changelog — Aperture

> State: stable · Optionality: low · Open to Change: append-only. Format: [Keep a Changelog](https://keepachangelog.com). Entries before 2026-06-10 reconstructed during Git migration from checkpoint logs, file timestamps, Pocket recordings, and Notion records.

## [Unreleased]
- **Training corpus live (2026-07-28):** every tap now archives the exact frame to a **private** Vercel Blob store (`donations/YYYY-MM-DD/<donation_id>.jpg`) and logs `image_url` + `image_sha256` beside the prediction in the Google Sheet. Photos were previously discarded, so no donation could ever become training data. Archiving is non-blocking — a storage failure records `archive_error` and the tap still succeeds.
- **Verified: Aperture has NEVER had an Azure Cosmos DB.** Zero references across every saved workflow version; the Cosmos DB belongs to the Branch Cam prototype (Phase 0, Antioch, ~Dec 2025–Jan 2026) per `docs/history/ORIGINS.md`.
- **Farmbrite:** mapped the live API from outside without a token — base `https://api.farmbrite.com/v1`; `inventory_types`, `products`, `crops`, `animals`, `contacts`, `tasks`, `transactions`, `orders` all exist (401), others 404. `scripts/farmbrite-setup.py` auto-detects the auth header and find-or-creates the "Aperture Donations" inventory type. Blocked only on the API token.
- **Production chain LIVE (2026-07-28):** Vercel prod relay → n8n (rewired) → NVIDIA NIM `llama-3.2-90b-vision-instruct` → Google Sheet. Verified end-to-end from off-site: 200 in 11.5 s, Sheet row written, all nodes green. Only the iPad→camera LAN hop remains unexercised.
- **Vision prompt v0.4-nim — fixes a severe parroting bug:** v0.3's filled-in example JSON caused the model to echo `48.4 lbs / conf 0.82` on a REAL empty dock. Types-only schema + anti-parrot rule + mandatory `response_format: json_object`. Regression suite (`scripts/vision-regression-test.py`) covers both an empty-dock negative control and a real-produce positive control.
- **No always-on server:** Dell/VPS both rejected — every always-on piece is a managed service; capture happens on the iPad at tap time (`docs/decisions/2026-07-28-no-always-on-server.md`).
- **Zero-typing on-site install:** `scripts/make-ipad-script.py` emits a pre-configured (gitignored) iPad build; `selftest` mode proves every hop in one tap; `camera-access/ipad/ONSITE-CARD.md` is the 4-step card.
- **Tooling:** `scripts/rewire-n8n-ipad-nim.py` (backup → verify → PUT → readback → `--restore`). Guards two n8n traps: in-place node-type changes are silently ignored, and credentials must live in the workflow's project.
- Security hygiene: untracked `.env.production.local` (held an expired Vercel OIDC token).
- **Camera path DECIDED (2026-07-22): iPad on-tap LAN pull of the mounted Hikvision.** Keeps the installed camera, no new hardware, no Mac. `camera-access/ipad/aperture-pull.js` (Scriptable HTTP-Digest client, verified vs RFC 2617) pulls the ISAPI frame at the tap → posts to the relay → n8n → NIM vision → Sheet. Relay `app/api/donate/route.ts` gains a backward-compatible `image_b64` passthrough. On-site ~10-min install runbook + decision record shipped. Fallbacks: low-cost LAN box; Hik-Partner Pro OpenAPI (parallel).
- **Standing process rule (2026-07-22):** continuous doc/state upkeep + auto-push feature branches, no prompting / no push-approval (AGENTS.md → "Continuous state upkeep + auto-push").
- **Camera-path correction (2026-07-22):** Hik-Connect cloud-pull is VERIFIED DEAD for this camera (pyezviz/pyezvizapi empty device list; hikconnect lib no capture method). Mounted Hikvision is LAN-only. See docs/methods/camera-connectivity.md. Dell/pyezviz bridge steps in NEXT-STEPS.md marked SUPERSEDED.
- **Vision provider:** standardized on NVIDIA NIM (OpenAI-compatible, open VLM) replacing the dry OpenAI node; `bridge/bridge.py` `/v1` gateway injects the upstream key server-side (n8n holds only BRIDGE_TOKEN).
- Accuracy method portfolio (docs/ACCURACY-ROADMAP.md): SKU scanning, training data, OCR, priors, scale-in-the-loop, hybrid routing — no single method presumed; >=95% reliable is the gate
- **Reality baseline (2026-06-10):** image model only; training data not yet attached; target = Cul2vate loading-dock produce. EnterpriseCo material is pitch-posture (see docs/BUSINESS.md)
- Cul2vate Mac→Dell bridge migration (Phases 2–5; paused since 2026-04-18, awaiting the client contact's camera serial + Farmbrite creds and a Dell RustDesk session)
- Farmbrite write path (gated on API key; workflow guard-skips to "Farmbrite skipped (pending key)")
- EnterpriseCo conveyor mode: sub-300 ms re-architecture (Jetson Orin Nano + Basler GigE + barcode trigger) pending pilot agreement
- Kitchen-test capture set for accuracy report (KITCHEN-TEST-INSTRUCTIONS.md; only IMG_0739 so far)

## 2026-05-07 — EnterpriseCo meeting package
### Added
- Static-mode demo: deterministic OpenCV ChArUco pipeline, harness, stub + OpenAI providers (`demo/`)
- Deploy containers: Dockerfile.bridge, Dockerfile.demo, compose, QUICKSTART (`deploy/`)
- EnterpriseCo conveyor architecture brief (`docs/EnterpriseCo-conveyor-architecture.md`)
- Auto-detected deployed board params: DICT_6X6_50, 8×10, 4.0" squares (legacy generator did NOT match)
### Context
Thu 8 AM Teams with the prospect contact; posture: static demo, conveyor pivot, paid pilot.

## 2026-04-20 — README architecture + resume guide

## 2026-04-18 — Dell migration prep
### Added
- DELL-SESSION.md runbook (Phases 2+3), the client contact outreach (serial + Farmbrite ask), Hik-Connect account
### Changed
- Mac bridge intentionally killed (Mac off Cul2vate LAN); n8n snapshot URL points at dead quick-tunnel until Phase 4

## 2026-04-17 — Live Cul2vate demo ✅
### Added
- Demo-proven end-to-end: iPad PWA → Vercel relay → n8n (16 nodes) → Google Sheet; light theme (cream + soft sage)
### Facts
- Camera: Hikvision AcuSense <device-serial>, manual focus, zoom locked; ChArUco board 36×44" Dibond on brick

## 2026-04-16 — Initial Aperture build
### Added
- Next.js 16 PWA (big-button UI), Vercel serverless relay with shared-token auth, n8n Cloud workflow, Mac camera bridge (socat IPv6 + cloudflared), ChArUco-calibrated vision prompts, scripts/check-state.sh

## Pre-history (Branch Cam era, ~Dec 2025–Feb 2026)
- n8n + OpenAI vision prototype at The Branch food bank (Antioch): Azure web app, Cosmos DB, anomaly-detection and ChArUco roadmap (see Notion "Branch Cam" page and `docs/history/ORIGINS.md`)
- Origin: scale bottleneck at The Branch via a contact at The Branch; 92–95% production accuracy, 98% test ceiling
