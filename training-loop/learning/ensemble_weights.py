"""Per-specialist vote weights.

When the v2.0 specialist ensemble comes online, each specialist's output
contributes to the final weight estimate. Not all specialists are equally
reliable — some may be systematically better per item_type, per container
class, etc. This module learns those weights.

For each specialist s and class c:
    accuracy(s, c) = 1 / (1 + mean_absolute_pct_error_last_N_days)
    weight(s, c)   = accuracy(s, c) / Σ accuracy(s', c) for all s'

v1 behavior: writes a neutral table (all specialists weighted equally) so
the ensemble code path works even before ground truth is flowing.
"""
from __future__ import annotations

import json
import logging
import math
import pathlib
from dataclasses import dataclass
from datetime import datetime, timezone

log = logging.getLogger(__name__)

SPECIALISTS = [
    "container_classifier",
    "food_classifier",
    "volume_estimator",
    "differential_comparator",
    "prior_image_retriever",
]


@dataclass
class SpecialistMetric:
    specialist: str
    mean_abs_pct_error: float
    n_samples: int


def _accuracy(metric: SpecialistMetric) -> float:
    return 1.0 / (1.0 + metric.mean_abs_pct_error)


def compute_weights(
    metrics: list[SpecialistMetric],
    config: dict,
    prior_weights: dict | None = None,
) -> dict[str, float]:
    """Normalized weights summing to 1.0, with EMA smoothing against priors."""
    cfg = config["ensemble"]
    alpha = cfg["weight_ema_alpha"]

    by_specialist = {m.specialist: m for m in metrics}
    raw = {s: _accuracy(by_specialist[s]) if s in by_specialist else 1.0 for s in SPECIALISTS}
    total = sum(raw.values())
    normalized = {s: v / total for s, v in raw.items()}

    if prior_weights:
        # EMA smoothing to avoid thrashing
        smoothed = {
            s: alpha * normalized[s] + (1 - alpha) * prior_weights.get(s, 1.0 / len(SPECIALISTS))
            for s in SPECIALISTS
        }
        # Re-normalize after EMA
        total = sum(smoothed.values())
        return {s: v / total for s, v in smoothed.items()}
    return normalized


def write_table(weights: dict[str, float], out_path: pathlib.Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_schema": {
            "description": "Per-specialist vote weights, summing to 1.0. The ensemble fusion code multiplies each specialist's weight-lb estimate by its weight, then sums.",
            "regenerated_by": "training-loop/learning/ensemble_weights.py",
            "regenerated_at": datetime.now(timezone.utc).isoformat(),
        },
        "weights": weights,
    }
    out_path.write_text(json.dumps(payload, indent=2))


def initial_neutral_table(out_path: pathlib.Path) -> None:
    """Call once on fresh install — gives every specialist equal weight."""
    weights = {s: 1.0 / len(SPECIALISTS) for s in SPECIALISTS}
    write_table(weights, out_path)
