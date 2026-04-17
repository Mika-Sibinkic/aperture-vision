"""Per-class bias multiplier.

Sits BETWEEN learned density (which reshapes the model's physical priors)
and final user-facing weight. This layer catches residuals that can't be
explained by density alone — model systematic bias in volume estimation,
container misclassification rate, etc.

multiplier = ema(true_weight / predicted_weight, half_life=14d)

Clamped to [min_multiplier, max_multiplier] so a bad batch can't move the
world. Lower ema_half_life than density because bias shifts can be
model-behavioral (e.g., after a gpt-4o version bump).
"""
from __future__ import annotations

import json
import logging
import math
import pathlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .ground_truth import GroundTruthEvent
from .safeguards import SafeguardViolation, clamp_delta_pct

log = logging.getLogger(__name__)


@dataclass
class BiasRecord:
    item_type: str
    multiplier: float
    n_samples: int
    last_updated: str
    using_learned: bool


def _ema_weight(age_days: float, half_life_days: float) -> float:
    return math.exp(-math.log(2) * age_days / half_life_days)


def update(
    item_type: str,
    events: list[GroundTruthEvent],
    config: dict,
    prior: Optional[BiasRecord] = None,
) -> tuple[BiasRecord, list[SafeguardViolation]]:
    violations: list[SafeguardViolation] = []
    cfg = config["bias_multiplier"]

    relevant = [
        e for e in events
        if e.item_type == item_type and e.predicted_weight_lbs and e.true_weight_lbs
    ]
    if len(relevant) < cfg["min_samples_before_use"]:
        return (BiasRecord(
            item_type=item_type,
            multiplier=1.0,
            n_samples=len(relevant),
            last_updated=datetime.now(timezone.utc).isoformat(),
            using_learned=False,
        ), [])

    now_ts = datetime.now(timezone.utc).timestamp()
    weighted_sum = 0.0
    weight_total = 0.0
    for e in relevant:
        ratio = e.true_weight_lbs / e.predicted_weight_lbs
        age_days = (now_ts - datetime.fromisoformat(e.timestamp).timestamp()) / 86400
        w = _ema_weight(age_days, cfg["ema_half_life_days"])
        weighted_sum += ratio * w
        weight_total += w

    raw = weighted_sum / weight_total
    clamped = max(cfg["min_multiplier"], min(cfg["max_multiplier"], raw))
    if clamped != raw:
        violations.append(SafeguardViolation(
            rule=f"bias[{item_type}].absolute_clamp",
            detail=f"raw {raw:.3f} outside [{cfg['min_multiplier']},{cfg['max_multiplier']}]",
            proposed=raw,
            accepted=clamped,
        ))

    if prior and prior.using_learned:
        capped, v = clamp_delta_pct(
            prior.multiplier, clamped,
            max_delta_pct=5.0,
            rule_name=f"bias[{item_type}].per_cycle_delta",
        )
        if v: violations.append(v)
        clamped = capped

    rec = BiasRecord(
        item_type=item_type,
        multiplier=clamped,
        n_samples=len(relevant),
        last_updated=datetime.now(timezone.utc).isoformat(),
        using_learned=True,
    )
    log.info("bias[%s]: multiplier=%.3f (raw %.3f, n=%d)", item_type, clamped, raw, len(relevant))
    return rec, violations


def write_table(records: dict[str, BiasRecord], out_path: pathlib.Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        k: v.multiplier for k, v in records.items() if v.using_learned
    }
    # Preserve a debug sidecar with the full records
    debug_path = out_path.with_suffix(".debug.json")
    debug_path.write_text(json.dumps({
        k: {
            "multiplier": v.multiplier,
            "n_samples": v.n_samples,
            "last_updated": v.last_updated,
            "using_learned": v.using_learned,
        } for k, v in records.items()
    }, indent=2))
    out_path.write_text(json.dumps(payload, indent=2))
