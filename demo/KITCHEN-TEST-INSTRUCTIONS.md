# Kitchen test capture: instructions for Mika

The harness is wired. We need 8-12 (image, true_weight_lbs) pairs to populate
the accuracy report before the EnterpriseCo call. ~30 minutes of work.

## Setup (5 min)

1. **Print the board.** `~/Downloads/Charuco Board 36x44 300dpi.png`. Print at
   the largest size your printer supports (letter / tabloid / poster; it doesn't
   matter, the math computes from the squares). Display on a tablet or second
   monitor in fullscreen if you don't want to print.
   - Already auto-verified: dictionary = `DICT_6X6_50`, 8×10 grid, 4"
     squares (in the 300dpi master file). Detection is bulletproof.
2. **Mount the board flat.** Tape it to a kitchen cabinet, prop it on a chair,
   or lean it against a wall. Avoid creases or curling.
3. **Fix a phone or webcam** at a stable angle ~3-5 ft from the board.
   - Steady angle is essential; the same camera position must be used for
     every test photo. A tripod or a stack of books works.
   - Diagonal-overhead is best (mimics the Cul2vate dock geometry).
4. **Mark a "staging zone"** in front of the board with masking tape (~2 ft ×
   2 ft is fine). All test items go inside this zone.

## Verify before you capture the full set (2 min)

Take ONE test photo (board visible + something simple in the zone, like a
mug). Drop the file into `aperture/demo/test-images/` and call it `verify_01.jpg`.

Then run:

```bash
cd "."
demo/.venv/bin/python demo/charuco_preprocessor.py demo/test-images/verify_01.jpg
```

You want to see:
- `"detected": true`
- `"markers_found"`: ≥ 20 (out of 40 max)
- `"quality"`: `"good"` or `"excellent"`
- `"distortion"`: `"none"` or `"slight"`

If detection fails:
- Bring the camera closer to the board, OR print bigger
- Add light; markers detect best at high contrast
- Reduce camera angle (closer to perpendicular to the board)
- Re-shoot, re-run

## Capture the test set (15 min)

Photograph 8-12 items. Mix:
- 3 produce (apple / onion / cucumber / banana / etc.)
- 3 packaged (cereal box / rice bag / can / chip bag)
- 3 mixed or odd-shape (handful of grapes, sliced bread, bunch of bananas)
- 2 controls (empty zone with just the ChArUco; establishes residual=0
  baseline; OR one obviously-out-of-zone item to test "inside_zone": false)

For each item:
1. Place it inside the taped staging zone.
2. **Weigh on a kitchen scale.** Record weight in lb to 2 decimals (1 lb =
   453.59 g; convert if your scale only does grams).
3. **Photograph with the fixed camera position.** Both the item AND the
   ChArUco board must be in frame.
4. Save the image to `aperture/demo/test-images/`. Filename like
   `kitchen_01_apple.jpg` or anything you'll remember.

## Tell me about each shot

Either edit `demo/manifest.yaml` directly (one entry per image), or just send
me a list like:

```
kitchen_01_apple.jpg          0.42  Honeycrisp apple
kitchen_02_cereal_box.jpg     1.15  unopened Cheerios family-size
kitchen_03_can_diced_tomato.jpg  0.91  Hunt's 28oz can
…
```

I'll add them to the manifest and run the full accuracy report.

## What "92-95% accuracy" means here

The harness reports:
- **mean absolute % error** (the headline number)
- distribution: % of items within 5 / 10 / 15 / 25% of true weight
- **per-image table** with predicted vs true vs ChArUco quality

We're aiming for mean absolute % error ≤ 15% on this v1 static-mode pipeline
(no learned density, no specialist ensemble). Anything better is upside.
For the EnterpriseCo call we're framing accuracy as "directionally good for advisory
pre-cube, not legal-for-trade", so even if a couple of items hit ±20%, the
story holds.

## Expected runtime

- Per image: ~3-8 s (vision call dominates)
- 12 images: ~1-2 min
- Plus ~$0.20 OpenAI cost for the whole run (gpt-4o vision)

## When you're done

Drop a Slack/iMessage with the test-set filenames + weights. I'll fold them
into the manifest, run the harness, and the accuracy report at
`demo/output/accuracy-report.md` becomes the live demo evidence for the
meeting.
