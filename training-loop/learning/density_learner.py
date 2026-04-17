"""Per-class density learner.

Static density tables (Open Food Facts averages) systematically misweigh
Cul2vate's regional supply chain. This module replaces lookup with
empirical learned density from observed (true_weight, measured_volume)
pairs, weighted by recency.

For each item_type:
    learned_density = ema(true_weight / measured_volume, half_life=30d)

When sample count < min_samples: fall back to lookup baseline.
When learned density drifts > max_deviation from baseline: refuse update,
log violation, keep prior value.
"""
from __future__ import annotations

import json
import logging
import math
import pathlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .ground_truth import GroundTruthEvent, filter_recent
from .safeguards import (
    SafeguardViolation,
    clamp_delta_pct,
    sanity_within_baseline,
)

log = logging.getLogger(__name__)


@dataclass
class DensityRecord:
    item_type: str
    density_lbs_per_cu_in_mean: float
    density_lbs_per_cu_in_stddev: float
    n_samples: int
    last_updated: str
    baseline_value: float
    using_learned: bool          # false = falling back to baseline


def _ema_weight(age_days: float, half_life_days: float) -> float:
    """exp(-ln(2) · age / half_life) — half_life=30d means 30-day-old reading
    contributes 50% as much as today's."""
    return math.exp(-math.log(2) * age_days / half_life_days)


def update(
    item_type: str,
    events: list[GroundTruthEvent],
    measured_volumes_cu_in: dict[str, float],   # donation_id → volume from vision
    baseline: float,
    config: dict,
    prior: Optional[DensityRecord] = None,
) -> tuple[DensityRecord, list[SafeguardViolation]]:
    violations: list[SafeguardViolation] = []
    cfg = config["density"]

    # Filter to events for this item_type with a measured volume available
    relevant = [
        e for e in events
        if e.item_type == item_type
        and e.donation_id in measured_volumes_cu_in
        and measured_volumes_cu_in[e.donation_id] > 0
    ]

    if len(relevant) < cfg["min_samples_before_use"]:
        log.info("density[%s]: %d samples < min %d — using baseline %.4f",
                 item_type, len(relevant), cfg["min_samples_before_use"], baseline)
        return (DensityRecord(
            item_type=item_type,
            density_lbs_per_cu_in_mean=baseline,
            density_lbs_per_cu_in_stddev=0.0,
            n_samples=len(relevant),
            last_updated=datetime.now(timezone.utc).isoformat(),
            baseline_value=baseline,
            using_learned=False,
        ), [])

    # EMA over (density per sample, weighted by recency)
    now_ts = datetime.now(timezone.utc).timestamp()
    weighted_sum = 0.0
    weight_total = 0.0
    densities: list[float] = []
    for e in relevant:
        density = e.true_weight_lbs / measured_volumes_cu_in[e.donation_id]
        age_days = (now_ts - datetime.fromisoformat(e.timestamp).timestamp()) / 86400
        w = _ema_weight(age_days, cfg["ema_half_life_days"])
        weighted_sum += density * w
        weight_total += w
        densities.append(density)

    new_mean = weighted_sum / weight_total
    stddev = (sum((d - new_mean) ** 2 for d in densities) / len(densities)) ** 0.5

    # Safeguard 1: per-cycle delta clamp
    if prior and prior.using_learned:
        clamped, v = clamp_delta_pct(
            prior.density_lbs_per_cu_in_mean,
            new_mean,
            cfg["max_per_cycle_delta_pct"],
            f"density[{item_type}].per_cycle_delta",
        )
        if v: violations.append(v)
        new_mean = clamped

    # Safeguard 2: sanity vs baseline
    ok, v = sanity_within_baseline(
        new_mean,
        baseline,
        cfg["sanity_max_deviation_from_baseline_pct"],
        f"density[{item_type}].baseline_deviation",
    )
    if not ok:
        violations.append(v)
        # Keep prior value rather than apply suspicious learned value
        return ((prior or DensityRecord(
            item_type=item_type,
            density_lbs_per_cu_in_mean=baseline,
            density_lbs_per_cu_in_stddev=0.0,
            n_samples=0,
            last_updated=datetime.now(timezone.utc).isoformat(),
            baseline_value=baseline,
            using_learned=False,
        )), violations)

    rec = DensityRecord(
        item_type=item_type,
        density_lbs_per_cu_in_mean=new_mean,
        density_lbs_per_cu_in_stddev=stddev,
        n_samples=len(relevant),
        last_updated=datetime.now(timezone.utc).isoformat(),
        baseline_value=baseline,
        using_learned=True,
    )
    log.info("density[%s]: learned %.4f ± %.4f (n=%d, baseline %.4f, Δ %.1f%%)",
             item_type, rec.density_lbs_per_cu_in_mean, rec.density_lbs_per_cu_in_stddev,
             rec.n_samples, baseline,
             (rec.density_lbs_per_cu_in_mean - baseline) / baseline * 100)
    return rec, violations


def write_table(records: dict[str, DensityRecord], out_path: pathlib.Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_schema": {
            "description": "Per-item-type learned density (lbs / cu_in). The n8n workflow fetches this and uses learned values where using_learned=true; falls back to baseline_value otherwise.",
            "regenerated_by": "training-loop/learning/density_learner.py",
            "regenerated_at": datetime.now(timezone.utc).isoformat(),
        },
        "densities": {
            k: {
                "density_lbs_per_cu_in_mean": v.density_lbs_per_cu_in_mean,
                "density_lbs_per_cu_in_stddev": v.density_lbs_per_cu_in_stddev,
                "n_samples": v.n_samples,
                "last_updated": v.last_updated,
                "baseline_value": v.baseline_value,
                "using_learned": v.using_learned,
            } for k, v in records.items()
        },
    }
    out_path.write_text(json.dumps(payload, indent=2))
