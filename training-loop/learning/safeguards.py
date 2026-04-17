"""Anti-hallucination guardrails shared by every learner.

Three categories:
  - Clamps           — bound a single cycle's parameter delta
  - Sanity checks    — bound learned values relative to physical baselines
  - Convergence-to-self detection — refuse to learn from our own predictions

If any safeguard fires, the offending update is rejected and a structured
`SafeguardViolation` is logged. The pipeline keeps running with the prior
parameter values; nothing is silently broken.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Optional

log = logging.getLogger(__name__)


@dataclass
class SafeguardViolation:
    rule: str
    detail: str
    proposed: object
    accepted: object


def clamp_delta_pct(
    old_value: float,
    new_value: float,
    max_delta_pct: float,
    rule_name: str,
) -> tuple[float, Optional[SafeguardViolation]]:
    """Bound a parameter's per-cycle change to ±max_delta_pct."""
    if old_value == 0:
        return new_value, None
    delta_pct = abs(new_value - old_value) / abs(old_value) * 100
    if delta_pct <= max_delta_pct:
        return new_value, None
    direction = 1 if new_value > old_value else -1
    capped = old_value * (1 + direction * max_delta_pct / 100)
    v = SafeguardViolation(
        rule=rule_name,
        detail=f"requested Δ={delta_pct:.2f}% > cap {max_delta_pct}%",
        proposed=new_value,
        accepted=capped,
    )
    log.warning("safeguard %s — clamping %.4f → %.4f (was %.4f)", rule_name, new_value, capped, old_value)
    return capped, v


def sanity_within_baseline(
    learned_value: float,
    baseline_value: float,
    max_deviation_pct: float,
    rule_name: str,
) -> tuple[bool, Optional[SafeguardViolation]]:
    """Reject learned values that drift too far from a known physical baseline."""
    if baseline_value == 0:
        return True, None
    dev = abs(learned_value - baseline_value) / baseline_value * 100
    if dev <= max_deviation_pct:
        return True, None
    v = SafeguardViolation(
        rule=rule_name,
        detail=f"learned={learned_value:.4f} vs baseline={baseline_value:.4f} ({dev:.1f}% deviation > {max_deviation_pct}% allowed)",
        proposed=learned_value,
        accepted=baseline_value,
    )
    log.error("safeguard %s — REJECTED %.4f (baseline %.4f, %.1f%% deviation)", rule_name, learned_value, baseline_value, dev)
    return False, v


def detect_convergence_to_self(
    ground_truth_sources: Iterable[str],
    rule_name: str = "convergence_to_self",
) -> tuple[bool, Optional[SafeguardViolation]]:
    """If >80% of recent ground truth came from our own predictions (e.g.,
    a hypothetical 'auto-confirm' loop) we'd be learning from ourselves.

    Currently every legitimate source is human-or-instrument-derived
    (scale_ocr, manual, farmbrite). This check exists as a circuit-breaker
    in case some future source ever feeds model output back as 'truth'.
    """
    sources = list(ground_truth_sources)
    if not sources:
        return True, None
    self_sources = {"model_prediction", "model_self_label"}  # forbidden source IDs
    self_count = sum(1 for s in sources if s in self_sources)
    if self_count / len(sources) <= 0.20:
        return True, None
    v = SafeguardViolation(
        rule=rule_name,
        detail=f"{self_count}/{len(sources)} samples came from model output — refusing to learn",
        proposed=sources,
        accepted=[],
    )
    log.critical("safeguard %s FIRED — pausing learning. detail=%s", rule_name, v.detail)
    return False, v
