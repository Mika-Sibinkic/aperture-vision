# Aperture — Static demo + accuracy harness

Built 2026-05-07 for the EnterpriseCo/the prospect contact meeting. Lives entirely on Mika's Mac;
no Dell, n8n, or Hik-Connect dependency.

## What this demonstrates

**Aperture's deterministic vision pipeline:** OpenCV ChArUco preprocessor
computes pixels-per-inch from real geometry → vision call (gpt-4o) receives
the calibration as an input rather than guessing → residual is computed
against ground-truth weights captured on a kitchen scale.

The architecture matters more than the numbers. This is the static-mode v1
pipeline. For EnterpriseCo's <500 ms in-motion conveyor target, see
`docs/EnterpriseCo-conveyor-architecture.md` — same core, different sensors and
runtime.

## File layout

```
demo/
├── charuco_preprocessor.py   # deterministic OpenCV ChArUco → ppi + bbox
├── vision_provider.py        # OpenAI gpt-4o + stub provider
├── harness.py                # main runner: image → ppi → vision → residual
├── auto_detect_board.py      # brute-force dictionary detection on any board image
├── manifest.yaml             # test set definition (image + true_weight_lbs)
├── run_demo.sh               # one-line runner (creates venv + runs)
├── test-images/              # IMG_0739 + Mika's kitchen captures
├── output/                   # residuals.jsonl + accuracy-report.md
└── KITCHEN-TEST-INSTRUCTIONS.md   # capture guide for Mika
```

## Run it

```bash
# from aperture/ repo root
bash demo/run_demo.sh                          # auto-detects key, falls back to stub
bash demo/run_demo.sh --provider openai        # explicit real run
bash demo/run_demo.sh --provider stub          # plumbing-only
```

The `run_demo.sh` script auto-installs the demo venv on first run.

## ChArUco board parameters (auto-verified)

| Setting | Value | Source |
|---|---|---|
| Dictionary | `DICT_6X6_50` | `auto_detect_board.py` against `~/Downloads/Charuco Board 36x44 300dpi.png` |
| Grid | 8 × 10 | 40 markers detected = 8×10/2 |
| Square size | 4.0" | 32×40" pattern in 36×44" Dibond → 32/8 |
| Pattern area | 32 × 40" | with 2" white border |
| Total markers | 40 | one per checker square |
| Total inner corners | 63 | (8-1)(10-1) |

**Note:** The legacy `Food-Bank-Inventory-Management/generate_charuco_board.py`
hardcoded `DICT_4X4_50` and 6" squares — that does NOT match the
AlphaGraphics-printed board actually deployed at Cul2vate. Use this folder's
defaults (DICT_6X6_50 / 4") for any new test set.

## What's NOT in this demo

By deliberate scope (so we ship before the call):

- ChArUco _runtime_ recalibration (we trust the printed geometry)
- Stereo / structured-light depth (single-RGB-camera v1)
- Edge inference / quantized CNN (cloud gpt-4o is fine for static)
- Conveyor / barcode-trigger (covered in `docs/EnterpriseCo-conveyor-architecture.md`)
- NTEP certification (not the product positioning)

These are the differences between static-mode v1 (this demo) and the EnterpriseCo
production architecture. They are explicitly the scope of the 30-day pilot.
