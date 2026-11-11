# Training loop: hidden-weight evaluation

> **`run_cycle.py` is not offline and can cost money.** It downloads product photos
> from Open Food Facts, then, if `OPENAI_API_KEY` is set, sends a batch of them to
> gpt-4o. Those are paid calls. `APERTURE_SCRAPE_N` and `APERTURE_EVAL_N` set the batch
> sizes. Without the key it scrapes and rebuilds the bias table only.

The offline check is the unit test:

```bash
pip install -r training-loop/requirements.txt pytest
python -m pytest -q training-loop
```

The one that matters most is `test_hidden_weight.py`: it proves the known weight never
reaches the vision prompt. CI runs the tests on every push.

## The mechanic

Feed the model images whose weight is known, hide the weight, ask for a prediction,
and record the residual. Residuals become a per-item bias multiplier.

```
 scrape ─▶ strip weight ─▶ predict ─▶ residual ─▶ bias table
```

None of this runs on a schedule, and the live workflow does not apply the bias table
yet: **Parse vision + tare + bias** in `n8n/aperture-workflow-ipad-nim.json` uses an
empty table.

## Who writes `public/bias-table.json`

`build_bias_table.py` owns it. It aggregates `residuals.jsonl` into one multiplier per
item and writes `../public/bias-table.json`. Classes with fewer than `--min-samples`
(default 5) residuals stay out, and a move larger than `--max-delta` (default 0.2) is
clamped and flagged. `run_cycle.py` calls it as its last step.

`learning/run_cycle.py` also writes the same file, from Google Sheet ground truth. The
last one to run wins, so run one or the other.

## Data requirements

Every training sample must have:

| Field | Required | Why |
|---|---|---|
| `image_bytes` | yes | what we feed the model |
| `weight_lbs` | yes | ground truth, stripped before prediction |
| `item_type` | yes | for per-class bias tracking |
| `source_url` | yes | for attribution / re-scraping |
| `camera_distance_proxy` | nice | if image looks like it was shot at similar range to our dock |
| `charuco_present` | usually false for scraped | flags whether scale reference exists |
| `background_type` | optional | "loading dock" / "studio" / "grocery shelf", noise dimension |

## Sources (ranked)

1. USDA FoodData Central: canonical weights per serving for raw produce, canned
   goods and bulk items. No images; pair with #2.
2. Open Food Facts: product photos with net weights. Free API. This is what
   `scraper.py` pulls today.
3. Farmbrite's own Cul2vate history: past harvest records with photo and weight.
   Same distribution as production.
4. Aperture's own production history, once real weights come back through
   `/api/correct` (not wired yet).
5. Synthetic generation: last resort, only for rare items with no real photos. Use
   real data. A blank is better than a fabricated sample.

## Hidden-weight protocol

The model **must never see the known weight at inference time**. Enforced by:

1. `scraper.py` saves the image to `images/<sha16>.jpg` and the metadata to
   `labels/<sha16>.json`. They are separate files.
2. `evaluator.py` reads the image only, builds the prompt, gets the prediction, then
   loads the label.
3. The prompt carries `eval_mode: true` and nothing from the label.
4. `test_hidden_weight.py` mocks the API call, captures the request body, and fails if
   the true weight appears in it as a number with a unit.

## Residual computation

```
residual_lbs   = |weight_lbs_true - weight_lbs_predicted|
residual_ratio = residual_lbs / weight_lbs_true
```

Per class:

- Mean absolute residual: the headline accuracy number.
- Mean ratio: bias direction. Above 1 for item X means the model overestimates X.
- Std of ratio: consistency. High std means the model is guessing.

Bias corrections are meant to apply downstream, as a per-class multiplier in the n8n
parse node, not by retraining the model.

## Rules

- Never let the model grade itself. Only real weighed items count as ground truth.
- If a multiplier moves more than 20% in a week, hold it for a human to approve.
  `build_bias_table.py --max-delta` enforces this.
- Review the ten worst residuals by hand before changing `prompts/weight-estimation.md`,
  and bump the prompt version when you do, so residuals attribute to the new prompt.

## Files

```
training-loop/
├── README.md                 # this file
├── run_cycle.py              # scrape → evaluate → build_bias_table (network, paid if keyed)
├── scraper.py                # Open Food Facts (and Farmbrite) → images/ + labels/
├── evaluator.py              # hidden-weight prediction → residuals.jsonl
├── build_bias_table.py       # residuals.jsonl → ../public/bias-table.json
├── test_hidden_weight.py     # the weight never reaches the prompt
├── learning/                 # Sheet-driven learning cycle (design, not running)
└── requirements.txt
```

`images/`, `labels/` and `residuals.jsonl` are created on first run. They are not in
the repo.

## Not in scope

- Fine-tuning a custom vision model. The loop stays on hosted models.
- Active learning (the model choosing what to label next). Sampling stays random.
- Multi-camera adaptation. Aperture is single-location, single-camera.
