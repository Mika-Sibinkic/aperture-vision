#!/usr/bin/env python3
"""Aperture Phase 2 — residual evaluator (production).

Hidden-weight protocol enforced:
  - Image bytes are loaded from images/<sha>.jpg.
  - Label (including weight) is loaded ONLY after the vision call returns.
  - The prompt sent to the vision API contains no reference to any known
    weight — see test_hidden_weight.py for automated proof.

Usage:
  OPENAI_API_KEY=sk-… python3 evaluator.py --provider openai --samples 20
  ANTHROPIC_API_KEY=sk-ant-… python3 evaluator.py --provider anthropic --samples 20
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
IMAGE_DIR = ROOT / "images"
LABEL_DIR = ROOT / "labels"
RESIDUAL_LOG = ROOT / "residuals.jsonl"
PROMPT_PATH = ROOT.parent / "prompts" / "weight-estimation.md"


@dataclass
class Prediction:
    weight_lbs: float | None
    item_type: str | None
    confidence: float | None
    raw: dict[str, Any]


def load_system_prompt() -> str:
    text = PROMPT_PATH.read_text()
    marker = "## System prompt"
    i = text.find(marker)
    if i == -1:
        raise RuntimeError(f"missing '{marker}' header in {PROMPT_PATH}")
    # Cut off "## User prompt template" and below so we don't leak template scaffolding.
    end = text.find("## User prompt template", i)
    return text[i: end if end != -1 else None].strip()


def prompt_fingerprint(system: str) -> str:
    return hashlib.sha256(system.encode()).hexdigest()[:10]


# ─── Provider adapters ──────────────────────────────────────────────────────

def call_openai(image_bytes: bytes, system: str, user: str, model: str) -> Prediction:
    key = os.environ["OPENAI_API_KEY"]
    b64 = base64.b64encode(image_bytes).decode()
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "response_format": {"type": "json_object"},
            "max_tokens": 800,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": user},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ]},
            ],
        }, timeout=60,
    )
    r.raise_for_status()
    parsed = json.loads(r.json()["choices"][0]["message"]["content"])
    return Prediction(
        weight_lbs=parsed.get("weight_lbs"),
        item_type=parsed.get("item_type"),
        confidence=parsed.get("confidence"),
        raw=parsed,
    )


def call_anthropic(image_bytes: bytes, system: str, user: str, model: str) -> Prediction:
    key = os.environ["ANTHROPIC_API_KEY"]
    b64 = base64.b64encode(image_bytes).decode()
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 800,
            "system": system,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": user + "\n\nRespond with JSON only."},
                ],
            }],
        }, timeout=60,
    )
    r.raise_for_status()
    content = r.json()["content"][0]["text"]
    # Claude may wrap in code fence — strip.
    if "```" in content:
        content = content.split("```")[1]
        if content.lstrip().startswith("json"):
            content = content.lstrip()[4:]
    parsed = json.loads(content)
    return Prediction(
        weight_lbs=parsed.get("weight_lbs"),
        item_type=parsed.get("item_type"),
        confidence=parsed.get("confidence"),
        raw=parsed,
    )


# ─── One-shot evaluation ────────────────────────────────────────────────────

def evaluate_one(sha: str, provider: str, model: str, system: str,
                 fingerprint: str, description: str = "") -> dict[str, Any]:
    img = (IMAGE_DIR / f"{sha}.jpg").read_bytes()

    user_message = (
        f"description: {description or '—'}\n"
        f"location: eval_harness\n"
        f"triggered_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"eval_mode: true"
    )

    if provider == "openai":
        pred = call_openai(img, system, user_message, model)
    elif provider == "anthropic":
        pred = call_anthropic(img, system, user_message, model)
    else:
        raise ValueError(f"unknown provider: {provider}")

    # Load label ONLY after prediction — enforces hidden-weight protocol.
    label = json.loads((LABEL_DIR / f"{sha}.json").read_text())
    true_lbs = float(label["weight_lbs"])

    residual_lbs: float | None = None
    residual_ratio: float | None = None
    if pred.weight_lbs is not None and true_lbs > 0:
        residual_lbs = abs(true_lbs - pred.weight_lbs)
        residual_ratio = residual_lbs / true_lbs

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "sha": sha,
        "item_type_label": label.get("item_type"),
        "item_type_pred": pred.item_type,
        "weight_lbs_true": true_lbs,
        "weight_lbs_pred": pred.weight_lbs,
        "residual_lbs": residual_lbs,
        "residual_ratio": residual_ratio,
        "confidence": pred.confidence,
        "provider": provider,
        "model": model,
        "prompt_fingerprint": fingerprint,
        "source": label.get("source"),
    }
    with RESIDUAL_LOG.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["openai", "anthropic"], default="openai")
    ap.add_argument("--model", default=None,
                    help="Override default model (gpt-4o or claude-sonnet-4-5)")
    ap.add_argument("--samples", type=int, default=10)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    model = args.model or ("gpt-4o" if args.provider == "openai" else "claude-sonnet-4-5")
    system = load_system_prompt()
    fingerprint = prompt_fingerprint(system)

    shas = sorted([p.stem for p in IMAGE_DIR.glob("*.jpg")])
    if not shas:
        print(f"no images in {IMAGE_DIR} — run scraper.py first", file=sys.stderr)
        sys.exit(2)
    if args.seed is not None:
        random.seed(args.seed)
    sample = random.sample(shas, min(args.samples, len(shas)))

    ok = 0
    bad = 0
    for sha in sample:
        try:
            record = evaluate_one(sha, args.provider, model, system, fingerprint)
            ratio = record["residual_ratio"]
            marker = f"{ratio*100:5.1f}%" if ratio is not None else "  skip"
            print(f"  {sha}  truth={record['weight_lbs_true']:6.2f} pred={record['weight_lbs_pred']}  ratio={marker}")
            ok += 1
        except Exception as e:
            print(f"  {sha}  FAILED: {e}", file=sys.stderr)
            bad += 1

    print(f"\n{ok} ok / {bad} failed  · log: {RESIDUAL_LOG}")


if __name__ == "__main__":
    main()
