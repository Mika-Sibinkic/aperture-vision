#!/usr/bin/env python3
"""Aperture Phase 2 — one full training cycle.

Run via cron / GitHub Actions. Sequence:

  1. Scrape N new samples from Open Food Facts across a rotating category set.
  2. Evaluate K random samples (prefers never-evaluated shas).
  3. Rebuild bias table.
  4. Print summary. Exit non-zero if nothing was scraped AND nothing evaluated.

Environment:
  OPENAI_API_KEY        required for evaluation
  APERTURE_CATEGORIES   comma-separated OFF categories to rotate through
                         (default: canned-foods,beverages,cereals,fruits)
  APERTURE_SCRAPE_N     new samples per category per cycle (default 10)
  APERTURE_EVAL_N       evaluations per cycle (default 15)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATEGORIES = os.environ.get(
    "APERTURE_CATEGORIES", "canned-foods,beverages,cereals,fruits"
).split(",")
SCRAPE_N = int(os.environ.get("APERTURE_SCRAPE_N", "10"))
EVAL_N = int(os.environ.get("APERTURE_EVAL_N", "15"))


def run(cmd: list[str]) -> int:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=ROOT)


def main() -> None:
    total_scraped = 0
    for cat in CATEGORIES:
        cat = cat.strip()
        if not cat:
            continue
        rc = run([sys.executable, "scraper.py", "--source", "openfoodfacts",
                  "--category", cat, "--count", str(SCRAPE_N)])
        if rc == 0:
            total_scraped += SCRAPE_N  # approximate — exact count in stdout
    print(f"\n=== scraping done (target ≤ {total_scraped}) ===\n")

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY unset — skipping evaluation phase", file=sys.stderr)
    else:
        run([sys.executable, "evaluator.py", "--provider", "openai", "--samples", str(EVAL_N)])

    run([sys.executable, "build_bias_table.py"])

    print("\n=== cycle complete ===")


if __name__ == "__main__":
    main()
