# Aperture

Aperture logs food donations with a camera instead of a scale. I built it at Null Systems
for [Cul2vate](https://cul2vate.org), a Nashville nonprofit that accepts produce
donations at the Ellington Ag Center. It grew out of an earlier prototype at The Branch
food bank.

**Who this is for:** people who run a donation or receiving dock and want a weight
logged for every load without stopping at a scale, and who can live with an estimate.

A volunteer stacks a donation inside the taped zone on the dock and taps one button on
an old iPad. The iPad pulls a frame from the mounted camera. A vision model names what
is in the zone and estimates its weight in pounds. The batch lands in a Google Sheet,
as a draft order in Farmbrite (the farm inventory system Cul2vate already uses), and as
a private copy of the photo. If the reading is wrong, the undo button is on the same
screen.

## Try it in a minute

Everything here runs offline and costs nothing. CI runs the same steps.

```bash
bash demo/run_demo.sh --provider stub
demo/.venv/bin/pip install -r training-loop/requirements.txt
demo/.venv/bin/python -m pytest -q training-loop demo/test_charuco.py
npm ci && npx tsc --noEmit && npm run build && npm test
npm run dev
```

I timed the first four lines from a fresh clone on my Mac (Python 3.14, Node 22). With
empty npm and pip caches they took 55 s. With warm caches, three runs took 36, 36 and
49 s. About half of each run is the demo installing OpenCV into its venv. You should see
`9 passed` from pytest and `24 passed` from the web tests.

The demo builds `demo/.venv`, looks for the printed ChArUco board in the two bundled
dock frames, and writes `demo/output/accuracy-report.md`. On my Mac it found:

```
- ChArUco detected: **1** / 2
| IMG_0739.JPG | 0.00 | 0.00 |  |  | ❌ |  | too_few_corners | 0.00s |
| dock-empty-night-IR.jpg | 0.00 | 0.00 |  |  | ✅ | 6.164 | poor | 0.00s |
```

The stub returns the manifest's true weight with up to 12% jitter. Both frames show an
empty dock, so the weight columns read 0 and only prove the plumbing works. The daytime
frame is a real failure: only 4 of the board's 40 markers are readable in it.
`demo/README.md` has the details.

The Python tests include one that proves the known weight never reaches the vision
prompt. The web tests cover the relay routes: the device token, input checks, duplicate
taps, undo and export. `npm run dev` serves the UI only, the legacy PWA on
`localhost:3000`. A tap there returns
`Server not configured: N8N_WEBHOOK_URL missing`, because the real path needs n8n, the
iPad and the camera.

## What a tap returns

I have not pasted a live response here, because capturing one writes a donation to
production. `python3 scripts/vision-regression-test.py --e2e` sends three control frames
through the live relay, prints the item and weight for each, and voids them. Their Sheet
rows stay: two say `REGRESSION TEST`, and the phantom control's says `Kale`. The relay passes through what the workflow's **Shape response** node
builds. The fields include `weight_lbs`, `item_type`, `container_type`, `container_count`, `weight_lbs_low`,
`weight_lbs_high`, `implausible_weight`, `prompt_version`, `model`,
`farmbrite_order_id` and `notes`.

## How it works

```
iPad (Scriptable)                          n8n Cloud (aperture-workflow-ipad-nim.json)
  tap ─▶ digest GET of a JPEG from the       1. check the shared token
         camera over the LAN                 2. NVIDIA NIM vision model → JSON
      ─▶ POST /api/donate ─────────────────▶ 3. >2000 lb flag
         (Next.js relay on Vercel;           4. Google Sheet row + Farmbrite draft
          archives the photo to Blob)        5. respond
      ◀── weight + IDs on the screen ◀───────
```

- **Capture.** Tested with a Hikvision AcuSense over ISAPI digest. The client is
  `camera-access/ipad/aperture-pull.js`.
- **Scale reference.** A printed ChArUco board hangs in the camera's view, so the
  model sees an object of known size in every frame. `demo/charuco_preprocessor.py`
  measures the board with OpenCV, but only in the offline demo, and it finds the board
  in 1 of the 2 bundled frames.
- **Prompt.** `prompts/weight-estimation.md` (v0.8-scene) is the file to change if you
  want the model to behave differently. It has the model count containers and name
  goods only inside the taped zone, return a types-only JSON schema, and answer
  "unidentified" or "empty" when that is the truth. Each version records the failure it
  fixes. `scripts/rewire-n8n-ipad-nim.py` pushes it into the workflow.
- **Learned priors: built, not wired.** `training-loop/learning/` computes per-item
  densities and bias multipliers, but the live workflow applies empty tables.

## Why it is built this way

The camera is LAN-only, and the iPad is already on the dock network at every tap, so
the iPad pulls the frame itself. That needs no on-site server and no new hardware
([decision](docs/decisions/2026-07-22-ipad-lan-bridge.md)). Vision runs on NVIDIA NIM
behind an n8n credential, so there is nothing of mine to keep alive. The trade is that
the free credits run out one day
([decision](docs/decisions/2026-07-28-no-always-on-server.md)). There is no scale on
the dock because the scale was the bottleneck: someone had to weigh and write down
every load. The price is that every weight is an estimate.

## Deploy your own

1. **n8n.** Import `n8n/aperture-workflow-ipad-nim.json` and follow `n8n/README.md`.
2. **NVIDIA NIM key.** Store it as the `NVIDIA NIM (Aperture)` credential in n8n.
3. **Google Sheet** with a `Donations` tab, connected through n8n's Google Sheets
   credential.
4. **Farmbrite (optional).** `scripts/farmbrite-setup.py` finds your IDs. Leave the
   Farmbrite variables blank and the workflow skips it.
5. **Vercel + Blob.** Deploy this repo to Vercel, create a private Blob store, and set
   the variables in the table below.
6. **iPad build.** Set `RELAY` at the top of `scripts/make-ipad-script.py` to your
   Vercel URL. Put the camera's address and login in a gitignored `SECRETS.local.md`
   as two lines, ``LAN: `<camera-ip>` `` and ``user `<user>` / pass `<password>` ``.
   Export `APERTURE_DEVICE_TOKEN` (the same value as in Vercel), run
   `python3 scripts/make-ipad-script.py`, then follow
   `camera-access/ipad/ONSITE-CARD.md`.

Hardware: one IP camera with a snapshot URL, one printed ChArUco board, and a spare
iPad running [Scriptable](https://scriptable.app). Bill of materials: `docs/BOM.md`.
Day-to-day operations: `docs/OPERATIONS.md`.

## Configuration

`.env.example` lists what the Vercel app reads:

| Variable | Read by |
|---|---|
| `N8N_WEBHOOK_URL` | `/api/donate`, to forward each tap to n8n |
| `APERTURE_SHARED_TOKEN` | `/api/donate` and `/api/correct`, sent to n8n's **Verify Token** node |
| `APERTURE_DEVICE_TOKEN` | Every `/api/*` route, checked against the `x-aperture-token` header. `scripts/make-ipad-script.py` bakes it into the iPad build |
| `BLOB_READ_WRITE_TOKEN` | `/api/donate` (archives the photo), `/api/void`, `/api/export` |
| `FARMBRITE_API_KEY` | `/api/void`, to delete the Farmbrite draft on undo |
| `N8N_CORRECTION_URL` | `/api/correct`. No workflow receives it yet |
| `NEXT_PUBLIC_LOCATION_LABEL` | `app/page.tsx`, the legacy PWA's location label |

The optional camera bridge has its own `bridge/.env.example` and
`deploy/.env.example`. Files that are local on purpose are not in the repo:
`SECRETS.local.md`, the generated `*.local.js` iPad build, Farmbrite CSV exports, and
the demo's generated `demo/output/`.

## Limits and security

The weights have not been checked against a scale on this camera. Treat the logged
pounds as an operational record and a trend, not audited poundage. The model's
self-reported confidence did not separate good readings from bad ones, so no operator
screen shows it. The relay checks a device token, but the check stays open until
`APERTURE_DEVICE_TOKEN` is set, so treat the relay URL as a secret until then. The
generated iPad build holds the camera password. The Next.js PWA in `app/` is legacy:
it posts no image, so it only works with one of the bridge-era workflows in `n8n/`.
`/api/correct` exists, but nothing on the n8n side receives corrections yet, so ground
truth does not flow back. What is secret and how to report a problem:
[SECURITY.md](SECURITY.md).

## Status

Live at Cul2vate since August 2026. `docs/OPERATIONS.md` is the record of what runs and
what breaks on its own. `CHANGELOG.md` has the history.

## Contributing

Issues and pull requests are welcome. Run the offline checks above first, and run
`scripts/vision-regression-test.py` against a live model for any prompt change.

## Provenance

This is the public copy of the private working repository, with the full commit history
preserved. Before publishing, `git-filter-repo` removed camera credentials, LAN and
hosting identifiers, a third party's confidential deal material, and personal contact
details from every commit. A placeholder company name and role descriptions stand in
for the removed names. Commits before 2026-06-10 were reconstructed from file timestamps
when the project moved into git.

Much of the code and documentation was written with Claude as a co-author.

## License

MIT. See `LICENSE`.
