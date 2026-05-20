"""
Vision provider abstraction for the demo harness.

Two providers:
  - openai (gpt-4o): the prod path. Requires OPENAI_API_KEY.
  - stub: returns a fake prediction equal to (true_weight ± 12% jitter)
    so the harness can be exercised end-to-end without a key. Tagged in
    every record so accuracy reports never confuse stub with real.
"""
from __future__ import annotations

import base64
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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


def call_vision(
    image_path: str,
    *,
    pixels_per_inch: float | None,
    board_bbox: list[int] | None,
    description: str = "",
    provider: str = "openai",
    model: str = "gpt-4o",
    true_weight_lbs: float | None = None,
) -> VisionPrediction:
    if provider == "stub":
        return _stub(image_path, true_weight_lbs)
    if provider == "openai":
        return _openai(image_path, pixels_per_inch, board_bbox, description, model)
    raise ValueError(f"unknown provider: {provider}")


def _stub(image_path: str, true_weight_lbs: float | None) -> VisionPrediction:
    """Deterministic-ish fake. Used when no API key is set so the wiring
    can be exercised end-to-end. Records are tagged provider=stub so they
    never get reported as real accuracy."""
    rng = random.Random(image_path)
    if true_weight_lbs is None:
        guess = round(rng.uniform(2.0, 50.0), 2)
    else:
        # ±12% jitter so the stub looks like a "92-95% accurate" model.
        jitter = rng.uniform(-0.12, 0.12)
        guess = round(true_weight_lbs * (1 + jitter), 2)
    return VisionPrediction(
        item_type="(stub)",
        weight_lbs=guess,
        weight_lbs_low=round(guess * 0.85, 2),
        weight_lbs_high=round(guess * 1.15, 2),
        confidence=0.7,
        inside_zone=True,
        charuco_detected_by_model=None,
        notes="STUB PROVIDER — no real vision call",
        provider="stub",
        model="stub",
        latency_s=0.0,
        raw={},
    )


SYSTEM_PROMPT_HEADER = """You are the vision component of Aperture, a vision-augmented dimensional-weight system. You analyze ONE photo per call.

Critical: a deterministic OpenCV preprocessor has ALREADY computed pixels_per_inch from the ChArUco calibration board in the frame. You DO NOT need to estimate calibration — use the value provided.

Return ONLY a JSON object with this schema (no markdown, no prose):
{
  "item_type": "short phrase describing the donation/parcel",
  "inside_zone": true,
  "charuco_detected_by_model": true,
  "estimated_volume_cu_in": 1728,
  "estimated_density_lbs_per_cu_in": 0.028,
  "weight_lbs": 48.4,
  "weight_lbs_low": 41.2,
  "weight_lbs_high": 56.0,
  "confidence": 0.82,
  "known_failure_flags": [],
  "notes": "one sentence, optional"
}

Estimation procedure:
1. Use the provided pixels_per_inch — do NOT re-estimate.
2. Identify the item(s) inside the staging zone or in the foreground (ignore the ChArUco board).
3. Estimate the bounding-box footprint and stack height in inches using pixels_per_inch.
4. volume = footprint_area * stack_height (cubic inches).
5. Density priors (rough, refine with context):
   - cardboard parcels (general mail): 0.005-0.020 lb/cu_in
   - packaged dry goods (cereal, pasta): 0.010-0.025 lb/cu_in
   - canned goods: 0.030-0.045 lb/cu_in
   - mixed produce: 0.012-0.022 lb/cu_in
   - fresh produce (loose): 0.015-0.025 lb/cu_in
   - leafy greens: 0.005-0.010 lb/cu_in
   - frozen meat cases: 0.035-0.050 lb/cu_in
   - dry beans/rice: 0.025-0.035 lb/cu_in
6. weight_lbs = volume * density. Provide a [low, high] range that reflects density-prior uncertainty.
7. confidence is calibrated. 0.95 = "I'd bet within 10%". 0.5 = "may be off by 50%".
8. If nothing is in the zone, set inside_zone=false and weight_lbs=null.

Hard constraints: JSON only, no narrative outside it."""


def _openai(
    image_path: str,
    pixels_per_inch: float | None,
    board_bbox: list[int] | None,
    description: str,
    model: str,
) -> VisionPrediction:
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set — either export it, or use --provider stub"
        )
    client = OpenAI(api_key=api_key)

    img_bytes = Path(image_path).read_bytes()
    b64 = base64.b64encode(img_bytes).decode()

    user_text = (
        f"pixels_per_inch (from OpenCV ChArUco preprocessor): {pixels_per_inch}\n"
        f"charuco_board_bbox_in_pixels (xmin,ymin,xmax,ymax): {board_bbox}\n"
        f"description: {description or '—'}\n"
        f"Estimate the weight of the item(s) outside the board bbox. "
        f"Respond with JSON only."
    )

    started = time.time()
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        max_tokens=600,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_HEADER},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            },
        ],
    )
    latency = time.time() - started
    content = resp.choices[0].message.content
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # GPT-4o very occasionally wraps in code fences despite json mode.
        cleaned = content.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()
        parsed = json.loads(cleaned)

    return VisionPrediction(
        item_type=parsed.get("item_type"),
        weight_lbs=parsed.get("weight_lbs"),
        weight_lbs_low=parsed.get("weight_lbs_low"),
        weight_lbs_high=parsed.get("weight_lbs_high"),
        confidence=parsed.get("confidence"),
        inside_zone=parsed.get("inside_zone"),
        charuco_detected_by_model=parsed.get("charuco_detected_by_model"),
        notes=parsed.get("notes", ""),
        provider="openai",
        model=model,
        latency_s=round(latency, 2),
        raw=parsed,
    )
