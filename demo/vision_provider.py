"""
Vision provider for the demo harness.

Two providers:
  - nim: the production path. The same prompt file, model and request as
    scripts/vision-regression-test.py, so there is one prompt and one model.
    Needs the NIM key in SECRETS.local.md.
  - stub: no vision call. Always answers 0 lb, whatever the true weight, so it
    exercises the wiring and can never pass for accuracy. Tagged provider=stub.
"""
from __future__ import annotations

import importlib.util
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


@dataclass
class VisionPrediction:
    item_type: str | None
    weight_lbs: float | None
    weight_lbs_low: float | None
    weight_lbs_high: float | None
    confidence: float | None
    inside_zone: bool | None
    charuco_detected_by_model: bool | None
    notes: str
    provider: str
    model: str
    latency_s: float
    raw: dict


def call_vision(image_path: str, *, description: str = "", provider: str = "stub") -> VisionPrediction:
    if provider == "stub":
        return _stub()
    if provider == "nim":
        return _nim(image_path, description)
    raise ValueError(f"unknown provider: {provider}")


def _stub() -> VisionPrediction:
    return VisionPrediction(
        item_type="(stub)",
        weight_lbs=0.0,
        weight_lbs_low=0.0,
        weight_lbs_high=0.0,
        confidence=None,
        inside_zone=None,
        charuco_detected_by_model=None,
        notes="STUB PROVIDER — no real vision call",
        provider="stub",
        model="stub",
        latency_s=0.0,
        raw={},
    )


def _regression_module():
    path = REPO / "scripts" / "vision-regression-test.py"   # hyphenated, so no plain import
    spec = importlib.util.spec_from_file_location("vision_regression_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def nim_model() -> str:
    return _regression_module().MODEL


def _nim(image_path: str, description: str) -> VisionPrediction:
    rt = _regression_module()
    started = time.time()
    parsed = rt.ask_nim(Path(image_path).read_bytes(), rt.nim_key(), description or "—")
    return VisionPrediction(
        item_type=parsed.get("item_type"),
        weight_lbs=parsed.get("weight_lbs"),
        weight_lbs_low=parsed.get("weight_lbs_low"),
        weight_lbs_high=parsed.get("weight_lbs_high"),
        confidence=parsed.get("confidence"),
        inside_zone=parsed.get("inside_zone"),
        charuco_detected_by_model=None,
        notes=parsed.get("notes") or "",
        provider="nim",
        model=rt.MODEL,
        latency_s=round(time.time() - started, 2),
        raw=parsed,
    )
