# Changelog: Aperture

Format: [Keep a Changelog](https://keepachangelog.com). Entries before 2026-06-10 are reconstructed from file timestamps.

## [Unreleased]

## [1.0.0] - 2026-11-11
First public release. First live taps at Cul2vate were on 2026-08-02, and it was last verified live that day. This release closes the gaps in the relay that a public URL would expose.

### Security
- Every `/api/*` route checks the `x-aperture-token` header against `APERTURE_DEVICE_TOKEN` with a constant-time compare and returns 401 on a miss. The check stays open while the variable is unset, so the live iPad keeps working until the token is rolled out. The iPad build and `scripts/vision-regression-test.py` send the header.
- CSV export prefixes `'` on any cell that starts with `=`, `+`, `-`, `@`, tab or CR, so Sheets and Excel do not run dock text as a formula.

### Fixed
- `/api/donate` no longer logs an n8n reply that carries an `error` (n8n answers 200 when it refuses the shared token). It returns 502, deletes the archived photo and writes no record.
- iPad: a build set up through the Keychain derives the export and undo URLs from the relay URL instead of placeholders, and the system check shows a failed undo as its own step.
- Prompt v0.9-board: the board has 4 in squares, not the 6 in that v0.8 stated. Committed only, not yet run against NIM or deployed.
- Farmbrite matcher: a generic word no longer lands on one variety ('potatoes' used to become Adirondack Blue Potatoes). A word matches a product it is part of only when exactly one product contains it, so 'carrot' still finds Carrots. Bucket products are never fuzzy-matched. November-May loads with no Seasonal bucket skip with a reason, and the response returns `farmbrite_skipped_reason`. Committed only, not deployed.
- The weight node is written whole by `scripts/rewire-n8n-ipad-nim.py` instead of patched. Its keyword resolver was rewriting the model's `container_type` from words in the notes. The Sheet columns keep their old constant values. Committed only, not deployed.
- `scripts/make-ipad-script.py` quotes every value it bakes in, so a backslash or quote in the camera password survives the build.
- iPad undo says the Sheet row stays. It used to say the donation was gone from the record.
- `/api/donate` keeps a client `donation_id` only when it is a UUID, coerces `description` to a string, and takes the blob date from a parsed timestamp. A numeric `description` used to return an empty-body 500.
- Duplicate donations: a retried tap whose first attempt is still running gets a 409 and never reaches n8n a second time. When n8n fails or returns nothing, the archived photo is deleted so the retry goes through.
- Undo marks a record voided only after the Farmbrite draft is deleted or none exists. A failed delete returns 502, keeps `farmbrite_void_error`, and the next undo retries it. The fallback lookup lists drafts and matches `ref <id>` exactly. `/api/void` rejects ids that are not UUIDs.
- CSV export returns 500 when any record fails to read, instead of a 200 with rows missing.

### Removed
- The legacy PWA (it posted no image and sent no device token), `/api/correct` (no caller, no workflow), `training-loop/` (nothing read its output, and its evaluator scored a different model from production), `public/bias-table.json`, `public/learned-state/`, `data/avg-weights.json`, `data/containers.json`, the offline ChArUco demo in `demo/` (production never ran it, and it had no weighed frames to score) and `scripts/farmbrite-setup.py` (it printed only the first 15 products and created an inventory type nothing uses). All are in git history.

### Changed
- `.env.example` lists exactly the five variables the app reads.
- `scripts/vision-regression-test.py` reads `RELAY` and `LOCATION` from `scripts/make-ipad-script.py`, so a fork sets each in one place.
- `scripts/rewire-n8n-ipad-nim.py` reads `N8N_WORKFLOW_ID` from the environment and takes credential ids from the nodes they are attached to.
- The test frames moved from `demo/test-images/` to `test-images/`, and the board parameters to `docs/BOM.md`.
- `data/donations-sheet-template.csv` has the columns the workflow writes.
- Removed the `lint` script. Next 16 dropped `next lint` and the repo has no ESLint config.
- Added vitest tests for the relay routes (`npm test`).

## 2026-06-10 to 2026-08-02: Live deployment at Cul2vate
- **First live capture from the mounted camera (2026-08-02): chain proven.** iPad system check passed on the dock: camera → relay → vision → Sheet → Farmbrite. The last unverified hop in the system is verified on real hardware.
- **Prompt v0.7-zone: fixes a confident false positive on the real camera.** The first live frame returned "banana box, 50 lbs" on an empty staging zone (night infrared, cluttered dock around the tape). Now: only goods inside the tape count, defaulting to a common container is forbidden, monochrome/IR is expected, and "unidentified" is an allowed answer. Verified: real frame → empty/0 lb, positive control still returns goods.
- **Negative control replaced with a real camera frame** (`demo/test-images/dock-empty-night-IR.jpg`), the exact frame that failed.
- Fixed: the regression suite was pinned to a model production does not use; it now reads the production model.
- Farmbrite live (2026-08-02): each tap writes a Draft order (`product_id` + `qty` in pounds). Verified against the real account and cleaned up. Non-blocking: Farmbrite down cannot fail a tap.
- Tare removed (prompt v0.6-net): v0.5 double-subtracted containers. The model's food-only weight is now the logged number; the fuzzy container lookup is out of the weight path. 60/60/60 lb across three runs of the same image.
- **Pre-handoff audit:** one on-site blocker (camera IP is DHCP and needs a reservation), plus four open risks: no alerting, NIM free credits, a user-scoped Farmbrite token, and accuracy not validated against a scale.
- Training corpus live (2026-07-28): every tap now archives the exact frame to a **private** Vercel Blob store (`donations/YYYY-MM-DD/<donation_id>.jpg`) and logs `image_url` + `image_sha256` beside the prediction in the Google Sheet. Photos were previously discarded, so no donation could ever become training data. Archiving is non-blocking: a storage failure records `archive_error` and the tap still succeeds.
- Farmbrite: mapped the live API from outside without a token. Base `https://api.farmbrite.com/v1`; `inventory_types`, `products`, `crops`, `animals`, `contacts`, `tasks`, `transactions`, `orders` all exist (401), others 404. `scripts/farmbrite-setup.py` auto-detects the auth header and find-or-creates the "Aperture Donations" inventory type. Blocked only on the API token.
- Production chain live (2026-07-28): Vercel prod relay → n8n (rewired) → NVIDIA NIM `llama-3.2-90b-vision-instruct` → Google Sheet. Verified end-to-end from off-site: 200 in 11.5 s, Sheet row written, all nodes green. Only the iPad→camera LAN hop remains unexercised.
- Vision prompt v0.4-nim fixes a severe parroting bug: v0.3's filled-in example JSON caused the model to echo `48.4 lbs / conf 0.82` on a REAL empty dock. Types-only schema + anti-parrot rule + mandatory `response_format: json_object`. Regression suite (`scripts/vision-regression-test.py`) covers both an empty-dock negative control and a real-produce positive control.
- No always-on server: Dell/VPS both rejected. Every always-on piece is a managed service; capture happens on the iPad at tap time (`docs/decisions/2026-07-28-no-always-on-server.md`).
- Zero-typing on-site install: `scripts/make-ipad-script.py` emits a pre-configured (gitignored) iPad build; `selftest` mode proves every hop in one tap; `camera-access/ipad/ONSITE-CARD.md` is the 4-step card.
- Tooling: `scripts/rewire-n8n-ipad-nim.py` (backup → verify → PUT → readback → `--restore`). Guards two n8n traps: in-place node-type changes are silently ignored, and credentials must live in the workflow's project.
- Security hygiene: untracked `.env.production.local` (held an expired Vercel OIDC token).
- **Camera path decided (2026-07-22): iPad on-tap LAN pull of the mounted Hikvision.** Keeps the installed camera, no new hardware, no Mac. `camera-access/ipad/aperture-pull.js` (Scriptable HTTP-Digest client, verified vs RFC 2617) pulls the ISAPI frame at the tap → posts to the relay → n8n → NIM vision → Sheet. Relay `app/api/donate/route.ts` gains a backward-compatible `image_b64` passthrough. On-site ~10-min install runbook + decision record shipped. Fallbacks: low-cost LAN box; Hik-Partner Pro OpenAPI (parallel).
- Camera-path correction (2026-07-22): Hik-Connect cloud-pull did not work for this camera (pyezviz/pyezvizapi empty device list; hikconnect lib no capture method). Mounted Hikvision is LAN-only. The Dell/pyezviz bridge steps are superseded.
- Vision provider: standardized on NVIDIA NIM (OpenAI-compatible, open VLM) replacing the dry OpenAI node; `bridge/bridge.py` `/v1` gateway injects the upstream key server-side (n8n holds only BRIDGE_TOKEN).
- Accuracy method portfolio (docs/ACCURACY-ROADMAP.md): SKU scanning, training data, OCR, priors, scale-in-the-loop, hybrid routing. No single method presumed; >=95% reliable is the gate
- Reality baseline (2026-06-10): image model only; training data not yet attached; target = Cul2vate loading-dock produce.
- Farmbrite write path (gated on API key; workflow guard-skips to "Farmbrite skipped (pending key)")
- Kitchen-test capture set for accuracy report (KITCHEN-TEST-INSTRUCTIONS.md; only IMG_0739 so far)

## 2026-05-07: Static demo and deploy containers
### Added
- Static-mode demo: deterministic OpenCV ChArUco pipeline, harness, stub + OpenAI providers (`demo/`)
- Deploy containers: Dockerfile.bridge, Dockerfile.demo, compose, QUICKSTART (`deploy/`)
- Auto-detected deployed board params: DICT_6X6_50, 8×10, 4.0" squares (the legacy generator did not match)

## 2026-04-20: README architecture + resume guide

## 2026-04-18: Dell migration prep
### Added
- Dell session runbook (Phases 2+3), camera serial + Farmbrite access request to Cul2vate, Hik-Connect account
### Changed
- Mac bridge intentionally killed (Mac off Cul2vate LAN); n8n snapshot URL points at dead quick-tunnel until Phase 4

## 2026-04-17: Live Cul2vate demo
### Added
- Demo-proven end-to-end: iPad PWA → Vercel relay → n8n (16 nodes) → Google Sheet; light theme (cream + soft sage)
### Facts
- Camera: Hikvision AcuSense <device-serial>, manual focus, zoom locked; ChArUco board 36×44" Dibond on brick

## 2026-04-16: Initial Aperture build
### Added
- Next.js 16 PWA (big-button UI), Vercel serverless relay with shared-token auth, n8n Cloud workflow, Mac camera bridge (socat IPv6 + cloudflared), ChArUco-calibrated vision prompts, scripts/check-state.sh

## Pre-history (Branch Cam era, ~Dec 2025 to Feb 2026)
- n8n + OpenAI vision prototype at The Branch food bank (Antioch): Azure web app, Cosmos DB, anomaly-detection and ChArUco roadmap
- Origin: scale bottleneck at The Branch via a contact at The Branch. No accuracy was measured there that this repo can show.
