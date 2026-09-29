# Aperture

Aperture is a donation-weighing camera for food-rescue loading docks. It was built by
Null Systems for [Cul2vate](https://cul2vate.org), a Nashville nonprofit that accepts
produce donations at the Ellington Ag Center, and it grew out of an earlier prototype
at The Branch food bank.

## What it does for Cul2vate

A volunteer stacks a donation inside the taped staging zone on the dock and taps one
button on an old iPad. The mounted camera grabs a frame, a vision model reads what is in
the zone and estimates its weight in pounds, and the batch is logged automatically: a row
in the Google Sheet, a draft order in Farmbrite (the farm inventory system Cul2vate
already uses), and a private copy of the photo. If the reading is wrong there is an undo
button on the same screen. No typing, no scale, no laptop on the dock.

## How it works

```
iPad (Scriptable script)                     n8n Cloud workflow
  tap ──▶ HTTP-digest snapshot from the        1. verify shared token
          IP camera over the LAN               2. vision model → structured JSON
       ──▶ POST /api/donate  ──────────────▶      (items, containers, food weight)
          (Next.js relay on Vercel;            3. plausibility guard, learned priors
           archives the photo to Blob)         4. Google Sheet row + Farmbrite order
       ◀── weight + IDs back to the screen ◀── 5. respond
```

- **Edge capture.** The iPad pulls a JPEG straight from the camera's ISAPI endpoint
  (any ONVIF/ISAPI-class IP camera with a snapshot URL works) and posts it to the relay.
  Nothing on the LAN needs to be reachable from the internet, and there is no always-on
  server on site (`docs/decisions/2026-07-28-no-always-on-server.md`).
- **Calibration.** A ChArUco board is mounted in the camera's view so the scene has a
  known physical scale (`demo/charuco_preprocessor.py`, `demo/auto_detect_board.py`).
- **Multimodal reasoning with structured output.** The prompt (`prompts/weight-estimation.md`,
  currently v0.8) asks the model to count containers and name goods only inside the taped
  zone, returns a types-only JSON schema, and treats "unidentified" and "empty" as valid
  answers. Each prompt version records the failure it fixes.
- **Historical density priors.** `training-loop/learning/` maintains per-item densities,
  bias multipliers and container references from ground-truth events, clamped per cycle,
  and publishes them as JSON under `public/learned-state/` for the workflow to read.

## Hardware

One PoE IP camera with a snapshot endpoint, one printed ChArUco board, one spare iPad
running [Scriptable](https://scriptable.app), and (optionally) one small Docker host if
you want the camera bridge instead of the iPad pull. The production install at Cul2vate
uses the iPad path and no on-site computer. Bill of materials: `docs/BOM.md`.

## Repository map

| Path | What |
|---|---|
| `app/`, `public/` | Next.js PWA and the `/api/donate`, `/api/correct`, `/api/void`, `/api/export` relay routes |
| `n8n/`, `prompts/` | Exported workflow versions; the versioned vision prompt |
| `camera-access/ipad/` | The on-site Scriptable client and install card |
| `bridge/`, `deploy/` | FastAPI camera bridge with a token-gated `/v1` vision proxy; Dockerfiles and compose |
| `demo/` | Deterministic ChArUco pipeline, harness and two real dock frames |
| `training-loop/` | Hidden-weight evaluator, scraper, learning loop, unit test |
| `docs/`, `scripts/` | Operations, runbooks, decisions, accuracy roadmap; setup, smoke and regression scripts |

## Running locally

PWA and relay:

```bash
npm install
cp .env.example .env.local
npm run dev
```

Camera bridge (the LAN-digest variant; `bridge/bridge.py` is the Hik-Connect variant):

```bash
python3 -m venv .bridge-venv && . .bridge-venv/bin/activate
pip install -r bridge/requirements.txt
export CAM_PASS='<camera password>' BRIDGE_TOKEN="$(openssl rand -hex 32)"
python bridge/mac_bridge.py
```

Or with Docker: fill in `deploy/.env.example` and follow `deploy/QUICKSTART.md`.

Training loop:

```bash
pip install -r training-loop/requirements.txt
python -m pytest -q training-loop
OPENAI_API_KEY=... python3 training-loop/run_cycle.py
```

`training-loop/README.md` describes the residual loop; `training-loop/learning/config.yml`
holds the learning-cycle limits.

## Status

Live at Cul2vate since August 2026 (`docs/OPERATIONS.md` is the authoritative operations
record; `docs/STATE.md` is a frozen June 2026 snapshot).

Validated on real hardware: the full chain (camera → relay → vision → Sheet → Farmbrite)
from an iPad tap on the dock; deterministic output for a given frame (60/60/60 lb across
three runs); an empty-zone negative control and a produce positive control in
`scripts/vision-regression-test.py`; Farmbrite writes against the real account; the
hidden-weight protocol under unit test.

Not validated: the weights themselves have not been checked against a scale on this
camera. Treat the logged pounds as an operational record and trend, not audited
poundage, until ground truth flows through `/api/correct`. The model's self-reported
confidence measured as uninformative and is hidden from every operator surface.

## Tests

There is one unit test, `training-loop/test_hidden_weight.py`, which proves the known
weight never reaches the vision prompt. CI runs it on every push. The vision regression
suite needs a live model endpoint and is run by hand.

## Provenance

This is the public copy of the private working repository, with the full commit history
preserved. Before publishing, `git-filter-repo` removed camera credentials, LAN and
hosting identifiers, a third party's confidential deal material, and personal contact
details from every commit; a placeholder company name and role descriptions stand in for
the removed names. Commits before 2026-06-10 were reconstructed from file timestamps
when the project moved into git.

Much of the code and documentation was written with Claude as a co-author.

## License

MIT. See `LICENSE`.
