# Method — ML / RL Continuity

> State: live · Optionality: HIGH · Open to Change: yes. Goal: every real donation yields training signal that tightens future predictions, with safeguards against drift and convergence-to-self.

Architecture + safeguards detail: [`../LEARNING-LOOPS.md`](../LEARNING-LOOPS.md). This file tracks **what runs vs. what's stubbed**, and the continuity rules.

## Verified working components (code exists + tested)

- **Hidden-weight evaluation** [VERIFIED by `training-loop/test_hidden_weight.py` in CI] — model never sees true weight at inference; image loaded → predict → *then* label loaded.
- **Public scraper** — Open Food Facts / USDA paths in `training-loop/scraper.py` (image+weight pairs to `images/` + `labels/`).
- **Residual logging** — `evaluator.py` → `residuals.jsonl` with prompt fingerprint + provenance.
- **Safeguards framework** — `training-loop/learning/safeguards.py`: per-cycle delta clamps, baseline sanity, convergence-to-self circuit breaker. Applied by every learner.

## Stubbed / aspirational (do NOT report as working)

- **Density learner** — `density_learner.py` runs but `measured_volume_cu_in` is a **stub** (v1.1 TODO at `learning/run_cycle.py`). Until vision emits volume, density learning falls back to baseline. [VERIFIED stub]
- **Ensemble weights** — neutral 0.2×5 seed; real per-specialist learning is v2.0. [VERIFIED scaffold]
- **Custom vision fine-tune** — explicitly out-of-scope in `training-loop/README.md`. The new fine-tune track (Qwen2.5-VL LoRA on dock captures) is **planned, not built**.
- **Ground-truth inflow** — `learned-densities.json` / `bias-table.json` are **empty**; no real donation has fed the loop. Cron (`aperture-learning.timer`, daily 3AM Dell) is wired but has no data.

## Continuity rules (must hold)

- Ground truth = scale OCR / manual correction / Farmbrite edit **only**. Model self-prediction as ground truth is forbidden (`safeguards.py` rejects it). [VERIFIED]
- Batched daily updates, not per-donation (noise control, readable git history).
- Every learned-state change is a git commit → Vercel redeploy → n8n picks up next run. Keep this continuous.
- Bias multipliers clamped [0.80, 1.25]; per-cycle delta ≤5%; learned values >30% off physical baseline rejected + flagged.

## Candidate improvements / open questions

- Close the density loop: surface `estimated_volume_cu_in` from the vision parse node → unstubs `density_learner`.
- The data harness (phase 1): Nutrition5k + Open Food Facts bootstrap → first real residual numbers **before** the camera is back.
- Promotion discipline: a new model/lever only replaces the baseline if it beats it on the held-out eval (NSOS variant-promotion mechanics: evidence threshold, no secondary-metric regression, rollback hash recorded).

## Change-log

- **2026-06-15** — Audited real-vs-stub status from primary sources. Confirmed [VERIFIED] no ground truth has ever fed the loop (`learned-densities.json`/`bias-table.json` empty); density volume + ensemble + fine-tune are stub/aspirational. Recorded continuity rules. Rollback: n/a (documentation only).


## Training corpus — LIVE as of 2026-07-28

Until now every captured frame was **discarded** after the vision call, so no
donation could ever become training data. That is fixed: the Vercel relay archives
the exact image it sent to the model before forwarding the tap.

| Piece | Where | Key |
|---|---|---|
| Photo (exact bytes sent to the model) | Vercel Blob, **private** store `<blob-store>`, path `donations/YYYY-MM-DD/<donation_id>.jpg` | `donation_id` |
| Prediction + tare/bias + model + prompt_version | Google Sheet `Donations` | `donation_id` |
| `image_url`, `image_sha256`, `image_bytes` | both | `image_sha256` dedupes re-taps of the same frame |
| Ground truth | `true_weight_lbs` column (empty until a real weight arrives) | joined on `donation_id` |

**Archiving is non-blocking by design** — a storage outage records `archive_error`
and the volunteer's tap still succeeds. Verified: a misconfigured access mode failed
the upload while the tap still returned a weight, and the reason was captured rather
than lost.

**Ground-truth sources, in order of value:**
1. **Farmbrite** — if staff record actual received weights, join on `donation_id`
   (written into the Farmbrite record) or on timestamp+item. Pending API token.
2. **Manual correction** — `app/api/correct/route.ts` already accepts
   `{donation_id, true_weight_lbs}`; it needs an n8n correction webhook
   (`N8N_CORRECTION_URL`) which does not exist yet.
3. Scale-in-the-loop OCR — future.

Once ~100–300 rows carry a real `true_weight_lbs`, the residual analysis in this
doc becomes runnable and a LoRA fine-tune on the paired (image, weight) corpus
becomes possible. Nothing else is needed to start accumulating — it accumulates
from the first volunteer tap.
