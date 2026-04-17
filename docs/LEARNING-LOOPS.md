# Aperture — Learning Loops Architecture

The system is designed so every real donation yields training signal that
tightens future predictions. Each component has its own RL loop, with
safeguards preventing drift, convergence-to-self, and single-sample
overreaction.

## The three tiers of learning

```
 ┌──────────────────────────────────────────────────────────────────┐
 │ TIER 3 — meta / pipeline                                         │
 │   prompt A/B tests, model selection, confidence calibration      │
 │   (manual for v1, automated in v2+)                              │
 └──────────────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────────────┐
 │ TIER 2 — per-class learners (this doc)                           │
 │   density_learner · bias_learner · classifier_learner            │
 │   ensemble_weights                                               │
 └──────────────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────────────┐
 │ TIER 1 — deterministic pre-processors                            │
 │   scale_ocr (ground truth)   charuco_preprocessor (v1.1)         │
 │   container tare lookup                                          │
 └──────────────────────────────────────────────────────────────────┘
```

## Ground-truth sources (ordered by reliability)

| Source | Reliability | How captured | When used |
|---|---|---|---|
| Scale OCR | High (~99% when LCD visible) | Tesseract reads dock platform scale LCD every snapshot | Every donation where scale is used |
| Manual correction | High (human-verified) | iPad "Edit weight" button → `/api/correct` → n8n → Sheet | Catches OCR misses |
| Farmbrite edit | Medium (delayed, human) | Cron poll of Farmbrite records we created, watching for weight edits | Backfill corrections |
| Model self-prediction | FORBIDDEN | N/A | Would cause convergence-to-self (guarded against in `safeguards.py`) |

## Per-component learning

### Density learner (`density_learner.py`)

**What it learns:** per item_type, the true `lbs / cu_in` density observed
from (scale_reading, vision_estimated_volume) pairs.

**Why it matters:** static Open Food Facts densities ignore regional +
seasonal variance. Tennessee October red onions ≠ California March red
onions. Learned density adapts per Cul2vate's actual supply chain.

**Algorithm:**
```
for each event e with (true_weight, measured_volume) in last 30d:
  density_i = true_weight_i / measured_volume_i
  age_weight_i = exp(-ln(2) · age_days / 30)
  
learned_density = Σ(density_i · age_weight_i) / Σ(age_weight_i)
```

**Safeguards:**
- Fallback to static baseline when n_samples < 5
- Per-cycle delta clamped to ±5% (one bad reading can't shift the world)
- Sanity check: reject if learned drifts > 30% from baseline (flags for
  human review — probably an OCR error)

### Bias multiplier learner (`bias_learner.py`)

**What it learns:** per item_type, the systematic ratio
`true_weight / predicted_weight` — catches model biases that density
alone can't explain (e.g., model consistently overestimates volume for
stacked items).

**Algorithm:** EMA of ratios over 14-day half-life.

**Safeguards:**
- Fallback to 1.0 when n_samples < 3
- Absolute clamp [0.80, 1.25] — never amplify beyond ±25%
- Per-cycle delta clamp ±5%

### Classifier reference sets (`classifier_learner.py`)

**What it learns:** growing library of misclassification examples for
container_classifier and food_classifier. Each entry is a
(past_image_url, correct_label) pair.

**Why it matters:** cheaper than fine-tuning, faster than retraining.
Few-shot prompting with 5-8 counter-examples per class can fix
systematic misclassifications.

**Algorithm:**
- When ground truth contradicts the model's classification, store the
  (image, correct_label) pair
- Per-class cap of 8 examples; drop older ones first
- 90-day max age (stale examples poison new-season predictions)
- On next inference, the prompt prepends: "Here are past images where
  the correct label was X…"

**Safeguards:**
- Keep_correct_examples=false — only teach from mistakes
- Dropped when too old OR when better examples arrive

### Ensemble weights (`ensemble_weights.py`)

**What it learns:** per specialist, the accuracy-based vote weight for
final weight fusion.

**v1 behavior:** writes neutral weights (0.2 each across 5 specialists).
Active role when v2.0 ensemble comes online.

**Algorithm:**
```
accuracy(s) = 1 / (1 + mean_abs_pct_error(s, last_14d))
weight(s) = accuracy(s) / Σ accuracy(s') for all s'
# smoothed with EMA α=0.15 against prior weights to prevent thrashing
```

## Cycle cadence

The learning cycle runs **daily at 3 AM** via
`aperture-learning.timer` on the Dell G7. Each cycle:

1. Pull new Sheet rows via service-account auth
2. Ingest any ground-truth not yet in the log
3. Abort if convergence-to-self detected
4. Recompute per-class densities and biases
5. Update classifier reference sets from misclassifications
6. Rewrite public/learned-state/\*.json
7. git commit + push → Vercel auto-deploys → n8n picks up on next run

**Why daily, not per-donation:** batched updates reduce noise, keep git
history readable, and let safeguards catch outlier days.

## Residual tracking

Every donation with a scale reading logs `residual_vs_scale_lbs` into the
Sheet. The training loop reads this to compute:

- `mean_residual_lbs_last_7d` per item_type
- `mean_abs_pct_error_last_7d` per item_type
- convergence rate per class (how fast residual is dropping)

When a class's residual stops dropping for 5+ consecutive cycles, that's
the signal to invest in the next tier (e.g., upgrade that class's
specialist, add more reference examples, or hit it with v2.0 ensemble).

## Expected convergence timeline

| Samples per class | Expected residual (well-behaved class) |
|---|---|
| 0-4 (baseline only) | ±20-25% |
| 5-15 (learned density kicks in) | ±12-18% |
| 15-50 (density + bias both active) | ±8-12% |
| 50-200 (reference sets stabilize) | ±5-9% |
| 200+ (ensemble + learned density saturated) | ±4-7% |

For high-variance classes (mixed produce, mixed donations), add ~3
percentage points to each tier.

## Anti-patterns that can never happen in this system

1. **Model learning from its own predictions** — safeguard rejects any
   ground-truth source named `model_prediction` or `model_self_label`.
2. **One bad day wrecks the table** — per-cycle delta clamps bound any
   parameter change to ≤5%.
3. **Drift past physical plausibility** — sanity check rejects learned
   values that deviate > 30% from known physical baselines.
4. **Stale classes taking over** — 90-day age limit on reference
   examples + 30-day EMA half-life on densities.
5. **Silent corruption** — every rejected update is logged as a
   `SafeguardViolation` and surfaced in the cycle summary.
