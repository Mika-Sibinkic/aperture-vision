"""Few-shot reference sets for container + food classifiers.

The teaching signal is misclassification. When ground truth contradicts the
model's container_type or food_type classification, we save the snapshot
URL + the correct label as a reference example. On the next donation, the
n8n workflow prepends these references to the specialist's system prompt
("here are N past photos where the correct answer was X, Y, Z") — a
permanent in-context correction that doesn't require retraining.

Storage: state/specialist-refs/<specialist>.jsonl
  { "image_url": str, "correct_label": str, "added_at": ISO, "reason": str }

Rotation:
  - Cap max N per class (default 8)
  - Drop entries older than max_age_days
  - Prioritize keeping rare-class examples over common-class examples
"""
from __future__ import annotations

import json
import logging
import pathlib
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Literal

log = logging.getLogger(__name__)

Specialist = Literal["container", "food"]


@dataclass
class ReferenceExample:
    image_url: str
    correct_label: str
    added_at: str
    reason: str             # "model_misclassified" | "low_confidence_correct"


def add_misclassification(
    specialist: Specialist,
    image_url: str,
    model_predicted: str,
    correct_label: str,
    state_dir: pathlib.Path,
    config: dict,
) -> None:
    """Append a new reference example. Rotation happens on prune() call."""
    cfg = config["classifier_reference_sets"]
    if model_predicted == correct_label:
        if not cfg["keep_correct_examples"]:
            return
    path = state_dir / f"{specialist}-ref.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    ex = ReferenceExample(
        image_url=image_url,
        correct_label=correct_label,
        added_at=datetime.now(timezone.utc).isoformat(),
        reason="model_misclassified" if model_predicted != correct_label else "low_confidence_correct",
    )
    with path.open("a") as f:
        f.write(json.dumps(asdict(ex)) + "\n")
    log.info("%s-ref: +example correct=%r (model said %r)", specialist, correct_label, model_predicted)


def prune(specialist: Specialist, state_dir: pathlib.Path, config: dict) -> int:
    """Enforce rotation rules. Returns # of entries kept."""
    cfg = config["classifier_reference_sets"]
    path = state_dir / f"{specialist}-ref.jsonl"
    if not path.exists():
        return 0

    cutoff_ts = datetime.now(timezone.utc).timestamp() - (cfg["max_age_days"] * 86400)
    by_class: dict[str, list[ReferenceExample]] = defaultdict(list)
    total_dropped_by_age = 0
    with path.open() as f:
        for line in f:
            if not line.strip():
                continue
            ex = ReferenceExample(**json.loads(line))
            if datetime.fromisoformat(ex.added_at).timestamp() < cutoff_ts:
                total_dropped_by_age += 1
                continue
            by_class[ex.correct_label].append(ex)

    # Per-class cap: keep the most recent max_refs_per_class per label
    kept: list[ReferenceExample] = []
    for label, exs in by_class.items():
        exs.sort(key=lambda e: e.added_at, reverse=True)
        kept.extend(exs[: cfg["max_refs_per_class"]])

    path.write_text("".join(json.dumps(asdict(e)) + "\n" for e in kept))
    log.info("%s-ref: pruned — kept %d, dropped %d old", specialist, len(kept), total_dropped_by_age)
    return len(kept)


def load_prompt_block(specialist: Specialist, state_dir: pathlib.Path) -> str:
    """Returns a text block to prepend to the specialist's system prompt.
    Safe to concatenate verbatim; emits empty string if no refs yet.
    """
    path = state_dir / f"{specialist}-ref.jsonl"
    if not path.exists():
        return ""
    lines: list[str] = []
    with path.open() as f:
        for i, raw in enumerate(f, start=1):
            if not raw.strip():
                continue
            ex = ReferenceExample(**json.loads(raw))
            lines.append(f"  {i}. url={ex.image_url}  correct_{specialist}_type={ex.correct_label!r}")
    if not lines:
        return ""
    return (
        f"REFERENCE EXAMPLES — here are past images where the correct "
        f"{specialist}_type was as annotated. Use them to calibrate your "
        f"classification on this image:\n" + "\n".join(lines) + "\n"
    )
