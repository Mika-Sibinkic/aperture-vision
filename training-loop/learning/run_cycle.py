#!/usr/bin/env python3
"""Daily learning-loop orchestrator.

Runs on the Dell G7 as a systemd timer (see systemd/aperture-learning.timer).
Steps:
  1. Pull fresh donation rows from the Google Sheet
  2. Split into (has_ground_truth) and (no_ground_truth yet)
  3. For each ground-truth sample, ensure it's appended to the log
  4. Update learned densities (per item_type)
  5. Update bias multipliers (per item_type)
  6. Update classifier reference sets (for container + food mis-classifications)
  7. Update ensemble weights (for v2.0 pipeline — currently neutral)
  8. Write JSON state files under public/learned-state/ for Vercel to serve
  9. Git-commit the updated state files
 10. Push to origin → Vercel redeploys → n8n picks up new params next run

The cycle is idempotent. Running it twice in a row is safe (second run
reads the same log + produces the same outputs).

Failure mode: any exception in a stage is caught, logged, and the remaining
stages continue. The Sheet is never mutated; state is only additive.
"""
from __future__ import annotations

import argparse
import logging
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

import yaml

from . import bias_learner, density_learner, ensemble_weights, ground_truth, sheets_puller
from .ground_truth import GroundTruthEvent
from .safeguards import detect_convergence_to_self

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
LEARNING_DIR = pathlib.Path(__file__).resolve().parent
STATE_DIR = LEARNING_DIR / "state"
PUBLIC_STATE_DIR = REPO_ROOT / "public" / "learned-state"
CONFIG_PATH = LEARNING_DIR / "config.yml"

# Baseline densities — seed values that learners fall back to until N samples
# are collected. Refined from Open Food Facts + common-sense physical bounds.
DENSITY_BASELINES = {
    "mixed produce":        0.017,
    "red onions":           0.019,
    "yellow onions":        0.019,
    "potatoes":             0.020,
    "apples":               0.018,
    "cased water bottles":  0.036,
    "canned goods":         0.040,
    "frozen ground beef":   0.038,
    "frozen meat cases":    0.042,
    "dry goods":            0.028,
    "rice":                 0.030,
    "beans":                0.028,
    "flour":                0.022,
    "leafy produce":        0.008,
    "lettuce":              0.006,
    "mixed greens":         0.007,
    "baked goods":          0.012,
    "bread":                0.010,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("learning-cycle")


def load_config() -> dict:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def parse_float(v) -> float | None:
    try:
        return float(v) if v not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None


def ingest_new_ground_truth(config: dict, sheet_id: str) -> list[GroundTruthEvent]:
    """Scan the Sheet for rows that have a true_weight_lbs filled in but
    haven't been logged yet. Returns list of new events appended this cycle."""
    log_path = STATE_DIR / "ground-truth-log.jsonl"
    seen_ids = {e.donation_id for e in ground_truth.load_all(log_path)}
    new: list[GroundTruthEvent] = []
    for row in sheets_puller.pull_rows(sheet_id):
        did = row.get("donation_id") or f"sheetrow-{row.get('__sheet_row')}"
        if did in seen_ids:
            continue
        true_weight = parse_float(row.get("true_weight_lbs")) or parse_float(row.get("scale_reading_lbs"))
        pred_weight = parse_float(row.get("weight_lbs_raw")) or parse_float(row.get("weight_lbs"))
        if true_weight is None or pred_weight is None:
            continue
        # Validate plausible bounds
        gt_cfg = config["ground_truth"]
        if not (gt_cfg["min_scale_reading_lbs"] <= true_weight <= gt_cfg["max_scale_reading_lbs"]):
            log.warning("ground_truth: skipping implausible weight %.2f in row %s", true_weight, did)
            continue
        source = row.get("ground_truth_source") or "scale_ocr"
        event = GroundTruthEvent.from_observation(
            donation_id=did,
            source=source,
            true_weight_lbs=true_weight,
            predicted_weight_lbs=pred_weight,
            item_type=(row.get("item_type") or "").strip().lower(),
            container_type=(row.get("container_type") or "").strip().lower(),
            confidence_reported=parse_float(row.get("confidence")) or 0.5,
        )
        ground_truth.append(event, log_path)
        new.append(event)
    return new


def cycle_once(sheet_id: str, dry_run: bool = False) -> dict:
    config = load_config()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_STATE_DIR.mkdir(parents=True, exist_ok=True)

    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "new_ground_truth_count": 0,
        "classes_updated": [],
        "violations": [],
    }

    # Stage 1: ingest ground truth
    try:
        new_events = ingest_new_ground_truth(config, sheet_id)
        summary["new_ground_truth_count"] = len(new_events)
        log.info("stage 1: ingested %d new ground-truth events", len(new_events))
    except Exception as e:
        log.exception("stage 1 ingest failed (continuing with existing log): %s", e)
        summary["ingest_error"] = str(e)
        new_events = []

    all_events = ground_truth.load_all(STATE_DIR / "ground-truth-log.jsonl")
    if len(all_events) < config["safeguards"]["min_new_samples_for_cycle"]:
        log.info("stage 2+: %d total events < min %d — skipping learner updates",
                 len(all_events), config["safeguards"]["min_new_samples_for_cycle"])
        return summary

    # Stage 2: convergence-to-self circuit breaker
    ok, v = detect_convergence_to_self([e.source for e in all_events])
    if not ok:
        summary["violations"].append(v.__dict__)
        log.critical("stage 2: convergence-to-self — ABORTING CYCLE")
        return summary

    # Stage 3: density learning (needs measured_volumes — fetched per donation)
    # In v1 we don't have per-donation volume logged yet — density_learner
    # gracefully falls back to baseline when volume is missing.
    # TODO v1.1: surface estimated_volume_cu_in from the parse-vision node
    # and write it to the Sheet so the learner has real volume data.
    densities: dict[str, density_learner.DensityRecord] = {}
    measured_volumes: dict[str, float] = {}  # donation_id → cu_in — v1.1 will populate
    item_types = {e.item_type for e in all_events if e.item_type}
    for item_type in item_types:
        baseline = DENSITY_BASELINES.get(item_type, 0.020)  # generic fallback
        try:
            rec, viols = density_learner.update(
                item_type=item_type,
                events=all_events,
                measured_volumes_cu_in=measured_volumes,
                baseline=baseline,
                config=config,
            )
            densities[item_type] = rec
            summary["violations"].extend([v.__dict__ for v in viols])
        except Exception as e:
            log.exception("density[%s] failed: %s", item_type, e)

    # Stage 4: bias learning (doesn't need volume — just (pred, true) pairs)
    biases: dict[str, bias_learner.BiasRecord] = {}
    for item_type in item_types:
        try:
            rec, viols = bias_learner.update(
                item_type=item_type,
                events=all_events,
                config=config,
            )
            biases[item_type] = rec
            summary["violations"].extend([v.__dict__ for v in viols])
        except Exception as e:
            log.exception("bias[%s] failed: %s", item_type, e)

    summary["classes_updated"] = sorted(item_types)

    # Stage 5: write state files
    density_learner.write_table(densities, PUBLIC_STATE_DIR / "learned-densities.json")
    bias_learner.write_table(biases, REPO_ROOT / "public" / "bias-table.json")

    # Stage 6: ensemble weights (neutral for v1 — real update at v2.0+)
    if not (PUBLIC_STATE_DIR / "ensemble-weights.json").exists():
        ensemble_weights.initial_neutral_table(PUBLIC_STATE_DIR / "ensemble-weights.json")

    # Stage 7: git commit + push
    if not dry_run:
        try:
            subprocess.run(["git", "-C", str(REPO_ROOT), "add",
                            "public/learned-state/", "public/bias-table.json",
                            f"Active Projects/Branch Cam Testing/aperture/training-loop/learning/state/"],
                           check=True, capture_output=True)
            status = subprocess.run(["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
                                    capture_output=True, text=True, check=True)
            if status.stdout.strip():
                subprocess.run(["git", "-C", str(REPO_ROOT), "commit",
                                "-m", f"[Aperture] learning cycle — {len(new_events)} new ground-truth, {len(item_types)} classes updated"],
                               check=True, capture_output=True)
                subprocess.run(["git", "-C", str(REPO_ROOT), "push"], check=True, capture_output=True)
                log.info("stage 7: git pushed")
            else:
                log.info("stage 7: nothing to commit")
        except subprocess.CalledProcessError as e:
            log.exception("stage 7 git failed: %s\n%s", e, e.stderr.decode() if e.stderr else "")
            summary["git_error"] = str(e)

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    log.info("cycle done: %s", summary)
    return summary


def main():
    ap = argparse.ArgumentParser(description="Aperture learning cycle")
    ap.add_argument("--sheet-id", required=True, help="Google Sheet ID (same as APERTURE_LOG_SHEET_ID)")
    ap.add_argument("--dry-run", action="store_true", help="don't git-commit/push")
    args = ap.parse_args()
    cycle_once(sheet_id=args.sheet_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
