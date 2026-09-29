# Phase 2: RL training loop (design)

**Scope of this file:** design + stubs. Full build is the follow-up chat.

## The core mechanic

A prediction-residual-update loop that runs independently of production
donations. It ingests **images with known weights**, hides the weight from
the vision model, asks the model to predict, computes residual, and uses
residuals to refine the prompt + per-item bias table.

```
 scrape ─▶ curate ─▶ strip metadata ─▶ predict ─▶ residual ─▶ update rules ─▶ redeploy prompt
   ▲                                                                                │
   └────────────────── continuous feed (cron-scheduled) ────────────────────────────┘
```

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

1. USDA FoodData Central: has canonical weights per serving for raw
   produce, canned goods, bulk items. Not images; pair with #2.
2. Open Food Facts: 2M+ product photos with net weights in grams/oz.
   Best single source; API is free.
3. Farmbrite's own Cul2vate history: past harvest records that include
   photo + weight. Gold standard; same distribution as production.
4. Aperture's own production history: once the client contact starts logging real
   weights via paper scale for the first N weeks, each of those is a
   residual sample.
5. Synthetic generation: LAST resort (per feedback_real_data_not_synthetic).
   Only useful for rare/edge item types where no real photos exist.

## Hidden-weight protocol

The model **must never see the known weight at inference time**. Enforced by:

1. Scraper saves image to `images/<sha256>.jpg` and metadata to
   `labels/<sha256>.json`. They're separate files.
2. Evaluator reads the image only, constructs the prompt with
   `eval_mode: true`, receives the prediction, then loads the label.
3. Prompt includes an explicit instruction: "If you see a weight in the
   metadata, ignore it; it is a test probe."
4. A unit test runs each release: feed the evaluator a sample, capture
   every prompt/message sent to the vision API, grep for any digit+unit
   pattern in metadata. Fail if found.

## Residual computation

```
residual_lbs   = |weight_lbs_true - weight_lbs_predicted|
residual_ratio = residual_lbs / weight_lbs_true
```

We track both. Per-class aggregates:

- Mean absolute residual (MAR): headline accuracy number
- Mean ratio (MR): bias direction. If mean_ratio > 1 for item X, model
  systematically overestimates X.
- Std of ratio: consistency. High std = model guessing.

Bias corrections are applied downstream (per-class multiplier in the
post-processing code node in n8n), NOT by retraining the model.

## Update cadence

- Per-sample: log residual to `residuals.jsonl` and
  `per_class_residuals.jsonl`.
- Weekly cron: recompute per-class bias multipliers, write to
  `bias_table.json`. n8n reads this file and applies in Parse-vision node.
- Monthly (manual): review the top-10 worst residuals by ratio. Are they
  a new class? A prompt failure mode? Update `prompts/weight-estimation.md`
  and bump the version. Residual tracking now attributes to the new prompt
  version so we can see if the edit helped.

## Anti-hallucination checks

Per CLAUDE.md adaptive-learning rules:

- Never let the model self-evaluate. Only Mika's / Cul2vate's real-weight
  comparisons count as ground truth.
- After 3 sessions with zero residuals logged, trigger reality check: are
  we sampling at all?
- If the bias-table multipliers move by >20% in a week, freeze updates and
  require Mika to approve before applying.

## What's in this directory

```
training-loop/
├── README.md              # this file
├── scraper.py             # stub: pulls from Open Food Facts API
├── evaluator.py           # stub: loads image, runs prompt, logs residual
├── bias_table.json        # computed weekly; consumed by n8n
├── requirements.txt       # minimal deps
└── residuals.jsonl        # append-only log (not committed)
```

## Not in scope for Phase 2

- Fine-tuning a custom vision model. We stay on API-hosted Claude/GPT-4o.
- Active learning (model choosing what to label next). Keep sampling random.
- Multi-camera adaptation. Aperture v1 is single-location, single-camera.
