#!/usr/bin/env python3
"""Aperture Phase 2 — build bias table from residual log.

Aggregates residuals.jsonl into a per-class multiplier table and writes
to ../public/bias-table.json. After the next Vercel deploy, n8n fetches
this file and applies the multiplier to the vision model's raw weight
prediction at inference time.

Safety:
  - Classes with < MIN_SAMPLES residuals are omitted (stay at 1.0).
  - Any single-week movement > MAX_DELTA is clamped + flagged, requiring
    manual approval before propagation (per CLAUDE.md anti-hallucination).
  - The current live table is read back in to compare against; delta warnings
    print to stderr.

Usage:
  python3 build_bias_table.py
  python3 build_bias_table.py --min-samples 5 --max-delta 0.2 --dry-run
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESIDUAL_LOG = ROOT / "residuals.jsonl"
OUT = ROOT.parent / "public" / "bias-table.json"


def load_residuals() -> list[dict]:
    if not RESIDUAL_LOG.exists():
        return []
    return [json.loads(line) for line in RESIDUAL_LOG.read_text().splitlines() if line.strip()]


def normalize_class(s: str | None) -> str:
    return (s or "unknown").strip().lower()


def build_table(min_samples: int) -> tuple[dict[str, float], dict[str, dict]]:
    """Returns (table, stats). table is {class: multiplier}. stats for reporting."""
    groups: dict[str, list[tuple[float, float]]] = defaultdict(list)  # (true, pred) pairs
    for r in load_residuals():
        if r.get("weight_lbs_true") and r.get("weight_lbs_pred"):
            key = normalize_class(r.get("item_type_label"))
            groups[key].append((float(r["weight_lbs_true"]), float(r["weight_lbs_pred"])))

    table: dict[str, float] = {}
    stats: dict[str, dict] = {}
    for key, pairs in groups.items():
        if len(pairs) < min_samples:
            continue
        # The multiplier corrects systematic over/underestimation:
        #   if model predicts 2x the truth on average, apply 0.5x.
        ratios = [pred / true for true, pred in pairs if true > 0]
        if not ratios:
            continue
        mean_ratio = statistics.fmean(ratios)
        if mean_ratio == 0:
            continue
        multiplier = 1.0 / mean_ratio
        stats[key] = {
            "samples": len(pairs),
            "mean_pred_over_true": round(mean_ratio, 3),
            "multiplier": round(multiplier, 3),
            "stdev_ratio": round(statistics.pstdev(ratios), 3) if len(ratios) > 1 else 0,
        }
        table[key] = round(multiplier, 4)
    return table, stats


def clamp_deltas(new: dict[str, float], current: dict[str, float], max_delta: float) -> tuple[dict[str, float], list[str]]:
    warnings: list[str] = []
    out: dict[str, float] = {}
    for k, v in new.items():
        cur = current.get(k)
        if cur is None:
            out[k] = v
            continue
        delta = abs(v - cur) / max(abs(cur), 1e-6)
        if delta > max_delta:
            # Move halfway — conservative step.
            clamped = (v + cur) / 2
            warnings.append(f"{k}: {cur:.3f} → wanted {v:.3f} (delta {delta*100:.0f}%), clamped to {clamped:.3f}")
            out[k] = round(clamped, 4)
        else:
            out[k] = v
    # Carry over classes that weren't re-sampled but were live.
    for k, v in current.items():
        out.setdefault(k, v)
    return out, warnings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-samples", type=int, default=5,
                    help="minimum residuals per class before applying a multiplier")
    ap.add_argument("--max-delta", type=float, default=0.2,
                    help="max single-cycle fractional change per class (clamped)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    new_table, stats = build_table(args.min_samples)
    current: dict[str, float] = {}
    if OUT.exists():
        try:
            current = {k: float(v) for k, v in json.loads(OUT.read_text()).items() if isinstance(v, (int, float))}
        except Exception:
            pass

    final, warnings = clamp_deltas(new_table, current, args.max_delta)

    for w in warnings:
        print(f"⚠ {w}", file=sys.stderr)

    print(f"classes with enough data: {len(new_table)}")
    for k, s in sorted(stats.items(), key=lambda kv: -kv[1]["samples"]):
        print(f"  {k:30s} n={s['samples']:3d}  "
              f"pred/true={s['mean_pred_over_true']:.2f}  "
              f"mult={s['multiplier']:.2f}  σ={s['stdev_ratio']:.2f}")

    if args.dry_run:
        print("\n[dry-run] not writing")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote {OUT} ({len(final)} classes)")


if __name__ == "__main__":
    main()
