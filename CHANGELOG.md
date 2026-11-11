# Changelog: Aperture

Format: [Keep a Changelog](https://keepachangelog.com).

## [Unreleased]

## [1.0.0] - 2026-11-11
First public release. First live taps at Cul2vate were on 2026-08-02, and it was last verified live that day. This release fixes the gaps in the relay that a public URL would expose. None of it is deployed yet.

### Security
- Every `/api/*` route checks the `x-aperture-token` header against `APERTURE_DEVICE_TOKEN` with a constant-time compare and returns 401 on a miss. The check stays open while the variable is unset, so the live iPad keeps working until the token is rolled out. The iPad build and `scripts/vision-regression-test.py` send the header.
- CSV export prefixes `'` on any cell that starts with `=`, `+`, `-`, `@`, tab or CR, so Sheets and Excel do not run dock text as a formula.

### Fixed
- `/api/donate` no longer logs an n8n reply that carries an `error` (n8n answers 200 when it refuses the shared token). It returns 502, deletes the archived photo and writes no record.
- iPad: a build set up through the Keychain derives the export and undo URLs from the relay URL instead of placeholders, and the system check shows a failed undo as its own step.
- Prompt v0.9-board: the board has 4 in squares, not the 6 in that v0.8 stated. Committed only, not yet run against NIM or deployed.
- Farmbrite matcher: a generic word no longer lands on one variety ('potatoes' used to become Adirondack Blue Potatoes). A word matches a product it is part of only when exactly one product contains it, so 'carrot' still finds Carrots. Bucket and Ministry products are never contains-matched; a Ministry product matches the name after 'Ministry ', singular or plural, so 'eggs' and 'egg' find Ministry Eggs. November-May loads with no Seasonal bucket skip with a reason, and the response returns `farmbrite_skipped_reason`. Committed only, not deployed.
- The weight node is written whole by `scripts/rewire-n8n-ipad-nim.py` instead of patched. Its keyword resolver was rewriting the model's `container_type` from words in the notes. The Sheet columns keep their old constant values. Committed only, not deployed.
- The rewire script redacts the shared token, every credential id and the Sheet id from the committed workflow, and refuses to write it otherwise. It used to mask only 64-hex strings. CI checks the committed file.
- iPad: the main screen's Undo asks with a native Alert. It used a WebView `confirm()`, which may never show in Scriptable.
- `scripts/make-ipad-script.py` quotes every value it bakes in, so a backslash or quote in the camera password survives the build.
- iPad undo says the Sheet row stays. It used to say the donation was gone from the record.
- `/api/donate` keeps a client `donation_id` only when it is a UUID, coerces `description` to a string, and takes the blob date from a parsed timestamp. A numeric `description` used to return an empty-body 500.
- Duplicate donations: a retried tap whose first attempt is still running gets a 409 and never reaches n8n a second time. When n8n fails or returns nothing, the archived photo is deleted so the retry goes through.
- Undo marks a record voided only after the Farmbrite draft is deleted or none exists. A failed delete returns 502, keeps `farmbrite_void_error`, and the next undo retries it. The fallback lookup lists drafts and matches `ref <id>` exactly. `/api/void` rejects ids that are not UUIDs.
- CSV export returns 500 when any record fails to read, instead of a 200 with rows missing.

### Removed
- The legacy PWA (it posted no image and sent no device token), `/api/correct` (no caller, no workflow), `training-loop/` (nothing read its output, and its evaluator scored a different model from production), `public/bias-table.json`, `public/learned-state/`, `data/avg-weights.json`, `data/containers.json`, the offline ChArUco demo in `demo/` (production never ran it, and it had no weighed frames to score) and `scripts/farmbrite-setup.py` (it printed only the first 15 products and created an inventory type nothing uses).
- The dead **Farmbrite skipped (pending key)** and disabled **Guard: Farmbrite configured** nodes, and the always-false `farmbrite_pending` and duplicate `farmbrite_id` response fields. Committed only, not deployed.

### Changed
- `.env.example` lists exactly the five variables the app reads.
- `scripts/vision-regression-test.py` reads `RELAY` and `LOCATION` from `scripts/make-ipad-script.py`, so a fork sets each in one place.
- `scripts/rewire-n8n-ipad-nim.py` reads `N8N_WORKFLOW_ID` from the environment and takes credential ids from the nodes they are attached to.
- The test frames moved from `demo/test-images/` to `test-images/`, and the board parameters to `docs/BOM.md`.
- `data/donations-sheet-template.csv` has the columns the workflow writes.
- Removed the `lint` script. Next 16 dropped `next lint` and the repo has no ESLint config.
- Added vitest tests for the relay routes (`npm test`).
- `scripts/vision-regression-test.py` reads `NIM_API_KEY`, and `scripts/make-ipad-script.py` reads `CAMERA_URL`, `CAMERA_USER` and `CAMERA_PASS`, before falling back to `SECRETS.local.md`.
- The CSV export no longer leads with `true_weight_lbs`; nothing writes it.

## Before 1.0
- 2026-07-22: The iPad pulls each frame from the mounted Hikvision over the LAN. Hik-Connect cloud pull did not work for this camera. [Decision](docs/decisions/2026-07-22-ipad-lan-bridge.md).
- 2026-07-28: No always-on server. Every always-on piece is a managed service, and capture happens on the iPad at tap time. [Decision](docs/decisions/2026-07-28-no-always-on-server.md).
- 2026-08-01: Vision moved from `llama-3.2-90b-vision-instruct` to `nvidia/nemotron-nano-12b-v2-vl` on NIM. The bigger model's slow runs went past the 15 s a tap is allowed.
- 2026-08-02: Tare removed from the weight path (prompt v0.6-net; it subtracted containers twice). Prompt v0.7-zone counts only goods inside the tape, after the first live frame of an empty zone came back as "banana box, 50 lbs".
- 2026-08-02: First live taps at Cul2vate. The iPad system check passed on the dock: camera, relay, vision, Sheet, Farmbrite.
