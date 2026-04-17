"""Aperture learning loop.

Stage-by-stage RL that turns every real donation into training signal.
Designed so every component's prediction is measurable against ground truth
and corrected on the next cycle — eventually driving residual toward the
scale's own measurement precision.

Modules
-------
ground_truth     Ingest ground-truth labels (scale OCR, manual corrections,
                 Farmbrite edits) and normalize into state/ground-truth-log.jsonl
density_learner  Per-class density EMA with anti-drift clamps
bias_learner     Per-class weight-prediction multiplier with safeguards
classifier_learner  Few-shot reference sets for container + food classifiers
ensemble_weights Per-specialist vote weights, learned from accuracy history
safeguards       Anti-hallucination, convergence-to-self, sanity checks
run_cycle        Daily orchestrator (systemd timer → git commit → redeploy)
"""

__version__ = "0.1.0"
