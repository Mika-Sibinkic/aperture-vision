# Aperture

Aperture logs food donations with a camera instead of a scale. I built it at Null Systems
for [Cul2vate](https://cul2vate.org), a Nashville nonprofit that accepts produce
donations at the Ellington Ag Center. It grew out of an earlier prototype at The Branch
food bank.

**Who this is for:** people who run a donation or receiving dock and want a weight
logged for every load without stopping at a scale, and who can live with an estimate.
The weights have not been checked against a scale yet, so nobody knows how far off
they are.

A volunteer stacks a donation inside the taped zone on the dock and taps one button on
an old iPad. The iPad pulls a frame from the mounted camera. A vision model names what
is in the zone and estimates its weight in pounds. The batch lands in a Google Sheet,
as a draft order in Farmbrite (the farm inventory system Cul2vate already uses), and as
a private copy of the photo. If the reading is wrong, the undo button is on the same
screen.

## Try it in a minute

The first two lines need nothing installed but Node. They run two nodes from the
committed workflow file against synthetic model replies: the weight node, which
decides what gets logged, and the Farmbrite matcher. Both carry fixes that are not
deployed yet (see Limits). The third line builds the relay and runs its tests. No
line needs an API key or makes a paid call.

```bash
node scripts/test_parse_vision.js
node scripts/test_farmbrite_match.js
npm ci && npx tsc --noEmit && npm run build && npm test
```

The first line prints what each model reply turns into:

````
model reply: empty zone, 0 lb               -> logged weight_lbs 0
model reply: 12.5 lb wrapped in ```json     -> logged weight_lbs 12.5
model reply: 2500 lb                        -> logged weight_lbs 2500  flagged implausible_weight
model reply: crate, notes mention a pallet  -> logged container_type crate
model reply: -5 lb                          -> logged weight_lbs 0
model reply: prose, not JSON                -> throws "Vision returned non-JSON", nothing logged
all parse-vision cases pass
````

I timed it from a fresh clone on my Mac (Node 22, `/usr/bin/time`): 0.02 s for each
node check, 8 s for the npm line with a warm npm cache. You should see `32 passed`. The
web tests cover the relay routes: the device token, input checks, duplicate taps,
retries after a failed n8n call, undo and export. CI runs all three lines on every
push, plus `scripts/check-ipad-script.sh`.

### Against the live model

`python3 scripts/vision-regression-test.py` sends the control frames straight to NIM
with the committed prompt and the production model, and writes nothing anywhere. It
needs a NIM key in `SECRETS.local.md` and spends NIM credits. `--e2e` sends three
control frames through your relay instead, prints the item and weight for each, and
voids them. Their Sheet rows stay: two say `REGRESSION TEST`, and the phantom
control's says `Kale`. The script shrinks frames with macOS `sips`; elsewhere it sends
them at full size.

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
- **Scale reference.** A printed ChArUco board (8×10 grid of 4 in squares,
  `docs/BOM.md`) hangs in the camera's view, so the model sees an object of known
  size in every frame. The prompt tells the model the square size. No code measures
  the board; the model reads it from the frame.
- **Prompt.** `prompts/weight-estimation.md` (v0.9-board) is the file to change if you
  want the model to behave differently. It has the model count containers and name
  goods only inside the taped zone, return a types-only JSON schema, and answer
  "unidentified" or "empty" when that is the truth. Each version records the failure it
  fixes. `scripts/rewire-n8n-ipad-nim.py` pushes it into the workflow. Its first line
  and its THE SCENE section describe Cul2vate's dock (a brick wall, a white van, the
  taped zone at centre-right); a fork rewrites both.
- **No learned corrections.** The weight node logs the model's number as it comes,
  clamped at 0 and flagged over 2000 lb. An earlier offline training loop scored a
  different model on product photos, so its corrections would not have fit
  production. It is in git history.

## Why it is built this way

The camera is LAN-only, and the iPad is already on the dock network at every tap, so
the iPad pulls the frame itself. That needs no on-site server and no new hardware
([decision](docs/decisions/2026-07-22-ipad-lan-bridge.md)). Vision runs on NVIDIA NIM
behind an n8n credential, so there is nothing of mine to keep alive. The trade is that
the free credits run out one day
([decision](docs/decisions/2026-07-28-no-always-on-server.md)). The model is
`nvidia/nemotron-nano-12b-v2-vl`. It replaced `llama-3.2-90b-vision-instruct` on
2026-08-01 because the bigger model's slow runs went past the 15 s a tap is allowed.
There is no scale on the dock because the scale was the bottleneck: someone had to
weigh and write down every load. The price is that every weight is an estimate.

## Deploy your own

Change these for your site:

- **The scene.** The first line and the THE SCENE section of the SYSTEM PROMPT in
  `prompts/weight-estimation.md`. Then run `scripts/vision-regression-test.py`. Its
  negative control, `test-images/dock-empty-night-IR.jpg`, is Cul2vate's empty dock;
  put an empty frame from your camera there under the same name.
- **`RELAY` and `LOCATION`** at the top of `scripts/make-ipad-script.py`. The
  regression test reads both from there. The `CONFIG` block in
  `camera-access/ipad/aperture-pull.js` holds the same two as defaults for a build
  set up by hand on the iPad.
- **`PRODUCT_MAP` and `NIM_MODEL`** in `scripts/rewire-n8n-ipad-nim.py`. Edit them
  there, not in the n8n node: the next rewire overwrites the node.
- **The Sheet ID** in the **Append to Google Sheet** node.

1. **n8n.** Import `n8n/aperture-workflow-ipad-nim.json` and follow `n8n/README.md`.
   To push prompt or mapping changes with `scripts/rewire-n8n-ipad-nim.py`, export
   `N8N_BASE_URL`, `N8N_API_KEY` and `N8N_WORKFLOW_ID`. The script takes the NIM and
   Farmbrite credential ids from the nodes they are attached to;
   `N8N_NIM_CREDENTIAL_ID` and `N8N_FARMBRITE_CREDENTIAL_ID` override them.
2. **NVIDIA NIM key.** Store it as the `NVIDIA NIM (Aperture)` credential in n8n.
3. **Google Sheet** with a `Donations` tab, connected through n8n's Google Sheets
   credential. Import `data/donations-sheet-template.csv` as that tab: its header is
   the columns the workflow writes.
4. **Farmbrite.** The workflow posts a Farmbrite draft order for every tap with a
   positive weight. No n8n variable turns that off. To skip Farmbrite, disable the
   **Farmbrite: log order** node. To use it, replace `PRODUCT_MAP` with your own
   products and run the rewire script. `n8n/README.md` step 4.
5. **Vercel + Blob.** Deploy this repo to Vercel, create a private Blob store, and set
   the variables in the table below.
6. **iPad build.** Set `RELAY` in `scripts/make-ipad-script.py` to your Vercel URL.
   Put the camera's address and login in a gitignored `SECRETS.local.md` as two lines, ``LAN: `<camera-ip>` `` and ``user `<user>` / pass `<password>` ``.
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
| `APERTURE_SHARED_TOKEN` | `/api/donate`, sent to n8n's **Verify Token** node |
| `APERTURE_DEVICE_TOKEN` | Every `/api/*` route, checked against the `x-aperture-token` header. `scripts/make-ipad-script.py` bakes it into the iPad build |
| `BLOB_READ_WRITE_TOKEN` | `/api/donate` (archives the photo), `/api/void`, `/api/export` |
| `FARMBRITE_API_KEY` | `/api/void`, to delete the Farmbrite draft on undo. Unset, undo skips Farmbrite, and fails for a tap that recorded an order id |

Files that are local on purpose are not in the repo:
`SECRETS.local.md`, the generated `*.local.js` iPad build and Farmbrite CSV exports.

## Limits

- The weights have not been checked against a scale on this camera. Treat the logged
  pounds as an operational record and a trend, not audited poundage. Nothing feeds
  scale weights back, so there is no ground truth.
- Across the first 10 live records the model's confidence took only two values, 0.85
  and 0.95. With no scale weights there is no way to check it, so no operator screen
  shows it.
- The committed workflow has three changes that are not deployed yet. Prompt
  v0.9-board gives the board's real 4 in squares; live still says 6 in. The Farmbrite
  matcher fix is what `test_farmbrite_match.js` checks. The weight node rewrite logs
  the model's `container_type` as it came. v0.9 has not been run against NIM.

## Security

- The relay checks a device token, but the check stays open until
  `APERTURE_DEVICE_TOKEN` is set. Treat the relay URL as a secret until then.
- The generated iPad build holds the camera password.
- What is secret and how to report a problem: [SECURITY.md](SECURITY.md).

## Status

First live taps at Cul2vate on 2026-08-02: the iPad system check plus the three
regression controls. `docs/OPERATIONS.md` records the state as last verified that day,
and is the record of what runs and what breaks on its own. `CHANGELOG.md` has the history.

## Contributing

Issues and pull requests are welcome. Run the three lines in "Try it in a minute"
first, and run `scripts/vision-regression-test.py` against a live model for any prompt
change.

## Provenance

This is the public copy of the private working repository. Commits before 2026-06-10
were reconstructed from file timestamps when the project moved into git.

Much of the code and documentation was written with Claude as a co-author.

## License

MIT. See `LICENSE`.
