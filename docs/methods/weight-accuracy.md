# Method: weight accuracy

> State: live · Optionality: HIGH · Open to Change: yes, recursively. Goal: **every reported item ≤5% weight error**, reliably (per Mika 2026-06-15), at Cul2vate, on open-top visible food/produce. Latency lax but **never slower than today**.

Full method portfolio + per-site selection logic: [`../ACCURACY-ROADMAP.md`](../ACCURACY-ROADMAP.md). This file tracks **what is measured** and **what method is live**.

## Verified working method (live in production)

**None yet.** [VERIFIED] The system has never been accuracy-verified against a scale. The only run produced a self-reported `confidence: 0.86`; confidence is not accuracy. No residual against ground truth has ever been recorded at Cul2vate.

Current pipeline (when the camera is up): deterministic ChArUco `pixels_per_inch` → hosted VLM (GPT-4o) volume×density estimate → tare/bias post-processing. Code: `demo/harness.py`, `demo/vision_provider.py`, `prompts/weight-estimation.md`.

## The ±5% reality (physics, research-grounded 2026-06-15)

±5% on **every** item from a single RGB frame is not reachable for heaped/mixed produce. Weight = volume × density; one photo can't see pile depth or air gaps.

| Case | Single-RGB error | Evidence |
|---|---|---|
| One regular item (apple, onion, squash) | ±4-7% | apple CNN 95.7%; plum MAPE ~7%; tomato ~93% [VERIFIED lit.] |
| Heaped / mixed loose produce | ±15-25% | Nutrition5k RGB mass error; EnterpriseCo brief ±15-25% [VERIFIED] |
| Item with scale in frame | ±0.5% | it's a measurement [VERIFIED] |

**Reachable reframe:** ±5% **blended, confidence-gated**: nail easy items, route un-nailable ones to a real reading. This is `ACCURACY-ROADMAP.md` #7 (scale-in-loop) + #8 (hybrid routing).

## Candidate levers (ranked for this scope): none verified yet

1. **Monocular metric depth** (UniDepthV2 / Depth-Anything-V2-metric / Metric3Dv2): metric volume from the *existing* single RGB. Biggest $0 software lever. [LIKELY]
2. Historical priors → Bayesian fusion: snap recurring items toward known weight distributions (`data/avg-weights.json` seed). Uses Cul2vate history (no images needed). [LIKELY]
3. 2nd view / iPad LiDAR depth: multi-view kills pile-depth ambiguity; ARKit depth if iPad is a Pro. [LIKELY, hardware-dependent]
4. **Per-item learned density** from going-forward dock captures (`density_learner.py`, currently volume-stubbed). [LIKELY]
5. Scale-in-the-loop (sampled / low-confidence): ±0.5% backstop + free ground truth. [VERIFIED principle]
6. **Depth camera** (RealSense D455 ~$389): true volume; phase-1.5 if monocular depth underperforms. [LIKELY]

## Measurement protocol (the gate before any lever is "verified")

Accuracy claims require: held-out eval set, hidden-weight protocol (`training-loop/evaluator.py`, enforced by `test_hidden_weight.py`), residual = |true−pred|/true per item-class. Metric: distribution of % error + share ≤5%. No lever graduates to "verified" without numbers from this harness.

## Change-log

- 2026-06-15: Established the baseline (none measured) and the research-grounded ±5% physics read. Logged the candidate-lever ranking for Cul2vate scope (single RGB, lax latency, open-top produce). Seeded item-weight prior `data/avg-weights.json` from the Cul2vate log template's Avg_Weights tab (synthetic seed; refine with real Farmbrite history). No production accuracy verified. Rollback: n/a (documentation + seed data).
