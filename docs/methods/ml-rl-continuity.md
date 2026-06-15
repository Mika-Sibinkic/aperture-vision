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
