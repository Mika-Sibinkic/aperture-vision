"""
Aperture demo harness — end-to-end accuracy run on a fixture set.

Pipeline per image:
  1. Deterministic OpenCV ChArUco preprocessor → pixels_per_inch + board bbox
  2. Vision provider (OpenAI gpt-4o or stub) → predicted weight + confidence
  3. Compare to manifest's true_weight_lbs → log residual

Output:
  output/residuals.jsonl — append-only record per image
  output/accuracy-report.md — human-readable summary

Usage:
  # full real run (needs OPENAI_API_KEY)
  python -m demo.harness --provider openai --manifest demo/manifest.yaml

  # plumbing test without an API key
  python -m demo.harness --provider stub --manifest demo/manifest.yaml
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Allow running both as `python -m demo.harness` and `python harness.py`
sys.path.insert(0, str(Path(__file__).resolve().parent))
import charuco_preprocessor  # noqa: E402
import vision_provider       # noqa: E402

ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "manifest.yaml"
DEFAULT_OUT = ROOT / "output"


def load_manifest(path: Path) -> dict:
    with path.open() as f:
        m = yaml.safe_load(f)
    if not isinstance(m, dict) or "images" not in m:
        raise ValueError(f"manifest {path} missing top-level 'images' list")
    return m


def evaluate_one(
    image_path: Path,
    *,
    true_weight_lbs: float | None,
    description: str,
    provider: str,
    model: str,
    board_squares_x: int,
    board_squares_y: int,
    board_square_in: float,
    board_dictionary: str,
) -> dict:
    started = time.time()

    # 1. Deterministic geometry.
    cha = charuco_preprocessor.analyze(
        str(image_path),
        squares_x=board_squares_x,
        squares_y=board_squares_y,
        square_size_in=board_square_in,
        dictionary_name=board_dictionary,
    )

    # 2. Vision call.
    try:
        pred = vision_provider.call_vision(
            str(image_path),
            pixels_per_inch=cha.pixels_per_inch,
            board_bbox=cha.board_pixel_bbox,
            description=description,
            provider=provider,
            model=model,
            true_weight_lbs=true_weight_lbs,
        )
        vision_error = None
    except Exception as e:
        pred = None
        vision_error = str(e)

    # 3. Residual.
    residual_lbs = None
    residual_ratio = None
    if (
        pred is not None
        and pred.weight_lbs is not None
        and true_weight_lbs is not None
        and true_weight_lbs > 0
    ):
        residual_lbs = round(abs(true_weight_lbs - pred.weight_lbs), 3)
        residual_ratio = round(residual_lbs / true_weight_lbs, 4)

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "image": image_path.name,
        "description": description,
        "true_weight_lbs": true_weight_lbs,
        "charuco": cha.to_dict(),
        "prediction": asdict(pred) if pred else None,
        "vision_error": vision_error,
        "residual_lbs": residual_lbs,
        "residual_ratio": residual_ratio,
        "wall_clock_s": round(time.time() - started, 3),
    }


def write_report(records: list[dict], out_md: Path, provider: str, model: str) -> None:
    rated = [
        r for r in records
        if r["residual_ratio"] is not None
        and r["prediction"]
        and r["prediction"]["provider"] != "stub"
    ]
    stub = [r for r in records if r["prediction"] and r["prediction"]["provider"] == "stub"]
    failed = [r for r in records if r["vision_error"] or not r["prediction"]]
    cha_detected = [r for r in records if r["charuco"]["detected"]]

    def pct(x): return f"{x*100:.1f}%"

    lines = [
        "# Aperture demo — accuracy report",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()} · provider={provider} · model={model}_",
        "",
        f"- Images run: **{len(records)}**",
        f"- Vision calls succeeded: **{len(records) - len(failed)}**",
        f"- Vision calls failed: **{len(failed)}**",
        f"- ChArUco detected: **{len(cha_detected)}** / {len(records)}",
        f"- Real (non-stub) ratings with ground truth: **{len(rated)}**",
        f"- Stub-provider runs (plumbing only): **{len(stub)}**",
        "",
    ]

    if rated:
        ratios = [r["residual_ratio"] for r in rated]
        lbs = [r["residual_lbs"] for r in rated if r["residual_lbs"] is not None]
        within_5 = sum(1 for r in ratios if r <= 0.05) / len(ratios)
        within_10 = sum(1 for r in ratios if r <= 0.10) / len(ratios)
        within_15 = sum(1 for r in ratios if r <= 0.15) / len(ratios)
        within_25 = sum(1 for r in ratios if r <= 0.25) / len(ratios)
        lines += [
            "## Real-vision accuracy",
            "",
            f"- Mean absolute % error: **{pct(statistics.mean(ratios))}**",
            f"- Median absolute % error: **{pct(statistics.median(ratios))}**",
            f"- p90 absolute % error: **{pct(sorted(ratios)[max(0, int(0.9*len(ratios))-1)])}**",
            f"- Mean absolute lb error: **{statistics.mean(lbs):.2f} lb**" if lbs else "",
            "",
            "### Distribution",
            f"- ≤  5% error: **{pct(within_5)}** of items",
            f"- ≤ 10% error: **{pct(within_10)}** of items",
            f"- ≤ 15% error: **{pct(within_15)}** of items",
            f"- ≤ 25% error: **{pct(within_25)}** of items",
            "",
        ]

    lines += ["## Per-image", "", "| Image | True (lb) | Pred (lb) | |Δ| | %err | ChArUco | ppi | Quality | Latency |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in records:
        pred = r["prediction"]
        cha = r["charuco"]
        true_lb = "" if r["true_weight_lbs"] is None else f"{r['true_weight_lbs']:.2f}"
        pred_lb = "" if not pred or pred["weight_lbs"] is None else f"{pred['weight_lbs']:.2f}"
        d_lb = "" if r["residual_lbs"] is None else f"{r['residual_lbs']:.2f}"
        pct_err = "" if r["residual_ratio"] is None else f"{r['residual_ratio']*100:.1f}%"
        cha_ok = "✅" if cha["detected"] else "❌"
        ppi = "" if cha["pixels_per_inch"] is None else f"{cha['pixels_per_inch']}"
        latency = "" if not pred else f"{pred['latency_s']:.2f}s"
        lines.append(
            f"| {r['image']} | {true_lb} | {pred_lb} | {d_lb} | {pct_err} | {cha_ok} | {ppi} | {cha['quality']} | {latency} |"
        )

    lines += ["", "## Method", "",
              "1. Deterministic OpenCV ChArUco preprocessor returns sub-pixel-accurate `pixels_per_inch` + board bbox.",
              "2. Vision call receives the calibration value as input (so the model never has to estimate it).",
              "3. Residual = |true - predicted| / true. No bias correction, no learned density — raw v1 numbers.",
              "",
              "## Honesty notes",
              "",
              "- This is the static-mode pipeline (no in-motion capture). For EnterpriseCo's <500ms conveyor target, see `docs/EnterpriseCo-conveyor-architecture.md`.",
              "- Stub-provider rows in the table do NOT contribute to the accuracy distribution. Tagged in residuals.jsonl as `provider=stub`.",
              "- ChArUco quality affects accuracy directly. 'Marginal' or 'poor' quality means the pixels-per-inch number itself is unreliable, so weight error compounds.",
              ""]
    out_md.write_text("\n".join([line for line in lines if line is not None]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--provider", default="openai", choices=["openai", "stub"])
    ap.add_argument("--model", default="gpt-4o")
    ap.add_argument("--output-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--limit", type=int, default=None,
                    help="run only N images (smoke test)")
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "residuals.jsonl"
    md_path = out_dir / "accuracy-report.md"

    manifest = load_manifest(Path(args.manifest))
    board = manifest.get("board", {})
    sx = int(board.get("squares_x", 8))
    sy = int(board.get("squares_y", 10))
    sz = float(board.get("square_size_in", 6.0))
    dictionary = board.get("dictionary", "DICT_4X4_50")

    image_root = Path(args.manifest).resolve().parent / manifest.get("image_dir", "test-images")
    images = manifest["images"][: args.limit] if args.limit else manifest["images"]

    records = []
    for entry in images:
        rel = entry["filename"]
        path = (image_root / rel).resolve()
        if not path.exists():
            print(f"  [skip] {rel}: not found at {path}", file=sys.stderr)
            continue
        try:
            rec = evaluate_one(
                path,
                true_weight_lbs=entry.get("true_weight_lbs"),
                description=entry.get("description", ""),
                provider=args.provider,
                model=args.model,
                board_squares_x=sx,
                board_squares_y=sy,
                board_square_in=sz,
                board_dictionary=dictionary,
            )
        except Exception as e:
            rec = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "image": rel,
                "description": entry.get("description", ""),
                "true_weight_lbs": entry.get("true_weight_lbs"),
                "charuco": {"detected": False, "quality": "harness_error"},
                "prediction": None,
                "vision_error": f"harness exception: {e}",
                "residual_lbs": None,
                "residual_ratio": None,
                "wall_clock_s": None,
            }
        records.append(rec)
        with jsonl_path.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        # Live one-line status for tail-watching.
        marker = "OK" if not rec.get("vision_error") else "ERR"
        cha_ok = "C+" if rec["charuco"]["detected"] else "C-"
        rr = "" if rec["residual_ratio"] is None else f" {rec['residual_ratio']*100:5.1f}%"
        print(f"  [{marker}] {cha_ok} {rel}{rr}")

    write_report(records, md_path, args.provider, args.model)
    print(f"\n  → {md_path}")
    print(f"  → {jsonl_path}")


if __name__ == "__main__":
    main()
