"""
Brute-force ArUco dictionary + grid detection for an unknown ChArUco image.

Run this on a single shot of the printed board (or even the source PNG).
Prints a row per (dictionary × grid) combo with the marker count detected.
The combo that detects the most markers is the right one for the harness.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

DICTS = [
    ("DICT_4X4_50", cv2.aruco.DICT_4X4_50),
    ("DICT_4X4_100", cv2.aruco.DICT_4X4_100),
    ("DICT_4X4_250", cv2.aruco.DICT_4X4_250),
    ("DICT_5X5_50", cv2.aruco.DICT_5X5_50),
    ("DICT_5X5_100", cv2.aruco.DICT_5X5_100),
    ("DICT_5X5_250", cv2.aruco.DICT_5X5_250),
    ("DICT_6X6_50", cv2.aruco.DICT_6X6_50),
    ("DICT_6X6_100", cv2.aruco.DICT_6X6_100),
    ("DICT_6X6_250", cv2.aruco.DICT_6X6_250),
    ("DICT_APRILTAG_36h11", cv2.aruco.DICT_APRILTAG_36h11),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    args = ap.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        print(f"cannot read {args.image}", file=sys.stderr)
        sys.exit(1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Tuned detection params (same as the production preprocessor).
    params = cv2.aruco.DetectorParameters()
    params.adaptiveThreshWinSizeMin = 3
    params.adaptiveThreshWinSizeMax = 23
    params.adaptiveThreshWinSizeStep = 5
    params.minMarkerPerimeterRate = 0.01
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX

    print(f"Image: {args.image}  ({img.shape[1]}×{img.shape[0]})")
    print(f"{'Dictionary':22s}  markers")
    best = None
    for name, did in DICTS:
        d = cv2.aruco.getPredefinedDictionary(did)
        det = cv2.aruco.ArucoDetector(d, params)
        corners, ids, _ = det.detectMarkers(gray)
        n = 0 if ids is None else len(ids)
        marker = "★" if n > 0 and (best is None or n > best[1]) else " "
        if n > 0 and (best is None or n > best[1]):
            best = (name, n, ids)
        print(f"  {marker}  {name:18s}  {n:4d}")

    if best:
        name, n, ids = best
        flat_ids = sorted({int(x[0]) for x in ids}) if ids is not None else []
        print(f"\nBest dictionary: {name}  ({n} markers, ids: {flat_ids[:20]}{'…' if len(flat_ids) > 20 else ''})")
    else:
        print("\nNo dictionary detected ANY markers in this image.")
        print("If this is a printed board, check: focus, lighting, contrast, scale.")
        print("If this is the source PNG, the file may not be a ChArUco board (could be a plain checkerboard).")


if __name__ == "__main__":
    main()
