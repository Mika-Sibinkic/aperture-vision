# Aperture: offline demo and accuracy harness

This folder runs a ChArUco board detector on two real frames from the Cul2vate dock: one
from the mounted camera, one an iPhone photo of its feed on a monitor. The stub run
needs no camera, no n8n and no API key. Production does not run this detector.

## What it does

`charuco_preprocessor.py` finds the printed ChArUco board with OpenCV and computes
pixels-per-inch from its known geometry. `harness.py` reports that, makes the vision
call, then computes the residual against the true weight in `manifest.yaml`. The
vision call does not receive the board numbers, same as production.

With `--provider stub` there is no vision call. The stub always answers 0 lb, so a stub
run tests the plumbing and the board detection, nothing else.

## Run it

```bash
bash demo/run_demo.sh --provider stub
```

The first run builds `demo/.venv` from `requirements.txt`. The report lands in
`demo/output/accuracy-report.md` (gitignored).

```bash
bash demo/run_demo.sh --provider nim
```

That sends each frame to NVIDIA NIM with the production prompt
(`prompts/weight-estimation.md`) and model, through the same `ask_nim` the regression
test uses. It needs the NIM key in `SECRETS.local.md`.

## What the board detection gets right and wrong

On the two bundled frames, the preprocessor finds the board in one:

| Frame | Markers found (of 40) | Result |
|---|---|---|
| `dock-empty-night-IR.jpg` | 27 | detected, 6.164 px/in, quality "poor" |
| `IMG_0739.JPG` (iPhone photo of a monitor) | 4 | not detected, moire leaves too few corners |

Measured on 2026-11-11 with the pinned `requirements.txt` (OpenCV 4.13), one run per
frame. The detector is deterministic, so a rerun gives the same table. The live
workflow does not run this preprocessor. In production the board is only a scale
reference the model can see in the frame.

## Files

| File | Role |
|---|---|
| `charuco_preprocessor.py` | OpenCV ChArUco detection, pixels-per-inch and board box |
| `auto_detect_board.py` | Tries every ArUco dictionary on an image and reports marker counts |
| `vision_provider.py` | NIM provider (production prompt and model) and the offline stub |
| `harness.py` | Image → preprocessor → vision → residual → report |
| `manifest.yaml` | Test set: image plus true weight in lb |
| `run_demo.sh` | Builds the venv and runs the harness |
| `test_charuco.py` | pytest: the detector's result on both bundled frames |
| `test-images/` | The two dock frames, both empty-zone controls |

## Board parameters

| Setting | Value |
|---|---|
| Dictionary | `DICT_6X6_50` |
| Grid | 8 × 10 squares |
| Square size | 4.0 in |
| Pattern area | 32 × 40 in, inside a 36 × 44 in print with a 2 in border |
| Markers | 40 |
| Inner corners | 63 |

`auto_detect_board.py` picked `DICT_6X6_50` on both bundled frames. An older generator
from the Branch prototype used `DICT_4X4_50` with 6 in squares, which does not match
the board printed for Cul2vate.

## Not in this demo

- Runtime recalibration. The harness trusts the printed geometry.
- Depth. It is a single RGB camera.
- A weighed test set. Both bundled frames are empty-zone controls with a true weight of
  0 lb, so this demo cannot measure weight error yet.
