"""Ground-truth ingestion — normalize signals from three sources:

  1. Scale OCR     (automatic, primary)  — read from image at donation time
  2. Manual edit   (iPad correction UI)   — PATCH a donation_id with true_lbs
  3. Farmbrite     (polled reconciliation) — the client contact edits the inventory record

Every ground-truth observation lands in state/ground-truth-log.jsonl as an
immutable event. Later learners aggregate from this log — never mutate it.

Schema (one JSON object per line):
{
  "donation_id": "uuid",
  "timestamp":   ISO-8601,
  "source":      "scale_ocr" | "manual" | "farmbrite",
  "true_weight_lbs": float,
  "predicted_weight_lbs": float,      # from the original donation row
  "item_type": str,
  "container_type": str,
  "residual_lbs": float,              # predicted - true
  "residual_pct": float,              # residual / true
  "confidence_reported": float,       # the model's self-reported confidence
  "confidence_bin": "high"|"mid"|"low"
}
"""
from __future__ import annotations

import json
import logging
import pathlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterable, Literal, Optional

log = logging.getLogger(__name__)

Source = Literal["scale_ocr", "manual", "farmbrite"]


@dataclass
class GroundTruthEvent:
    donation_id: str
    timestamp: str
    source: Source
    true_weight_lbs: float
    predicted_weight_lbs: float
    item_type: str
    container_type: str
    residual_lbs: float
    residual_pct: float
    confidence_reported: float
    confidence_bin: str

    @classmethod
    def from_observation(
        cls,
        donation_id: str,
        source: Source,
        true_weight_lbs: float,
        predicted_weight_lbs: float,
        item_type: str,
        container_type: str,
        confidence_reported: float,
    ) -> "GroundTruthEvent":
        residual = predicted_weight_lbs - true_weight_lbs
        residual_pct = residual / true_weight_lbs if true_weight_lbs else 0.0
        bin_ = "high" if confidence_reported >= 0.8 else "mid" if confidence_reported >= 0.5 else "low"
        return cls(
            donation_id=donation_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source=source,
            true_weight_lbs=true_weight_lbs,
            predicted_weight_lbs=predicted_weight_lbs,
            item_type=item_type,
            container_type=container_type,
            residual_lbs=residual,
            residual_pct=residual_pct,
            confidence_reported=confidence_reported,
            confidence_bin=bin_,
        )


def append(event: GroundTruthEvent, log_path: pathlib.Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps(asdict(event), default=str) + "\n")
    log.info(
        "ground_truth: +%s item=%r container=%r pred=%.2f true=%.2f residual=%.2f (%.1f%%)",
        event.source, event.item_type, event.container_type,
        event.predicted_weight_lbs, event.true_weight_lbs,
        event.residual_lbs, event.residual_pct * 100,
    )


def load_all(log_path: pathlib.Path) -> list[GroundTruthEvent]:
    if not log_path.exists():
        return []
    out: list[GroundTruthEvent] = []
    with log_path.open() as f:
        for line in f:
            if line.strip():
                out.append(GroundTruthEvent(**json.loads(line)))
    return out


def filter_recent(events: Iterable[GroundTruthEvent], days: int) -> list[GroundTruthEvent]:
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
    return [
        e for e in events
        if datetime.fromisoformat(e.timestamp).timestamp() > cutoff
    ]
