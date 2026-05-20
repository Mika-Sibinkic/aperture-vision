"""
Aperture ChArUco preprocessor — DETERMINISTIC.

Replaces the LLM's pixels-per-inch estimate with a textbook OpenCV pipeline:
detect ArUco markers, interpolate Charuco corners, derive sub-pixel positions,
compute pixels-per-inch from known geometry, return everything the downstream
volume estimator needs.

Why deterministic matters: same input → same output, every time. The vision
LLM was doing this math on vibes (and getting 5–15% wrong). OpenCV gets it
±1–2% from the same input. This is the single highest-ROI fix on the V2
agenda, hoisted forward for the EnterpriseCo demo.

Tunable defaults match the Cul2vate deployed board (8×10 grid of 6"
squares, DICT_4X4_50). Overridable via CLI for the kitchen test set Mika
prints from `Charuco Board 36x44 300dpi.png`.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np


# ── Board specs (override via CLI) ────────────────────────────────────────────
# Auto-detected via demo/auto_detect_board.py against the deployed AlphaGraphics
# print (Charuco Board 36x44 300dpi.png): DICT_6X6_50, 8×10 grid, 4" squares.
# Pattern occupies 32×40" centered on a 36×44" sheet (2" white border).
DEFAULTS = {
    "squares_x": 8,
    "squares_y": 10,
    "square_size_in": 4.0,
    "marker_ratio": 0.75,
    "dictionary": "DICT_6X6_50",
}


@dataclass
class CharucoResult:
    detected: bool
    pixels_per_inch: float | None
    ppi_std_dev: float | None
    ppi_cv: float | None  # coefficient of variation (lower = more consistent)
    quality: str
    markers_found: int
    markers_expected: int
    corners_found: int
    corners_expected: int
    distortion: str
    distortion_ratio: float | None
    image_width_px: int
    image_height_px: int
    board_pixel_bbox: list[int] | None  # [x_min, y_min, x_max, y_max]
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _get_dict(name: str):
    table = {
        "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
        "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
        "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
        "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
        "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
        "DICT_6X6_50": cv2.aruco.DICT_6X6_50,
        "DICT_APRILTAG_36h11": cv2.aruco.DICT_APRILTAG_36h11,
    }
    if name not in table:
        raise ValueError(f"Unknown ArUco dictionary: {name}")
    return cv2.aruco.getPredefinedDictionary(table[name])


def _build_detector(dictionary, params: cv2.aruco.DetectorParameters):
    """Detector tuned for long-range outdoor + variable-quality phone shots."""
    params.adaptiveThreshWinSizeMin = 3
    params.adaptiveThreshWinSizeMax = 23
    params.adaptiveThreshWinSizeStep = 5
    params.minMarkerPerimeterRate = 0.01
    params.maxMarkerPerimeterRate = 4.0
    params.polygonalApproxAccuracyRate = 0.05
    params.minCornerDistanceRate = 0.02
    params.minDistanceToBorder = 1
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    params.cornerRefinementWinSize = 5
    params.cornerRefinementMaxIterations = 30
    return cv2.aruco.ArucoDetector(dictionary, params)


def analyze(
    image_path: str,
    *,
    squares_x: int = DEFAULTS["squares_x"],
    squares_y: int = DEFAULTS["squares_y"],
    square_size_in: float = DEFAULTS["square_size_in"],
    marker_ratio: float = DEFAULTS["marker_ratio"],
    dictionary_name: str = DEFAULTS["dictionary"],
) -> CharucoResult:
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"cannot read {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    dictionary = _get_dict(dictionary_name)
    params = cv2.aruco.DetectorParameters()
    detector = _build_detector(dictionary, params)

    board = cv2.aruco.CharucoBoard(
        size=(squares_x, squares_y),
        squareLength=square_size_in,
        markerLength=square_size_in * marker_ratio,
        dictionary=dictionary,
    )

    total_markers_expected = (squares_x * squares_y) // 2
    total_corners_expected = (squares_x - 1) * (squares_y - 1)

    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None or len(ids) < 4:
        return CharucoResult(
            detected=False, pixels_per_inch=None, ppi_std_dev=None, ppi_cv=None,
            quality="not_detected", markers_found=0 if ids is None else len(ids),
            markers_expected=total_markers_expected, corners_found=0,
            corners_expected=total_corners_expected, distortion="unknown",
            distortion_ratio=None, image_width_px=w, image_height_px=h,
            board_pixel_bbox=None,
            notes="too few ArUco markers detected — check board print quality, lighting, focus, or dictionary",
        )

    markers_found = len(ids)

    # Interpolate Charuco corners from the detected markers.
    try:
        ret, c_corners, c_ids = cv2.aruco.interpolateCornersCharuco(
            corners, ids, gray, board
        )
    except Exception as e:
        return CharucoResult(
            detected=False, pixels_per_inch=None, ppi_std_dev=None, ppi_cv=None,
            quality="interpolation_failed", markers_found=markers_found,
            markers_expected=total_markers_expected, corners_found=0,
            corners_expected=total_corners_expected, distortion="unknown",
            distortion_ratio=None, image_width_px=w, image_height_px=h,
            board_pixel_bbox=None, notes=f"interpolation error: {e}",
        )

    if c_corners is None or c_ids is None or len(c_corners) < 4:
        return CharucoResult(
            detected=False, pixels_per_inch=None, ppi_std_dev=None, ppi_cv=None,
            quality="too_few_corners", markers_found=markers_found,
            markers_expected=total_markers_expected,
            corners_found=0 if c_corners is None else len(c_corners),
            corners_expected=total_corners_expected, distortion="unknown",
            distortion_ratio=None, image_width_px=w, image_height_px=h,
            board_pixel_bbox=None, notes="not enough Charuco corners interpolated",
        )

    corners_found = len(c_corners)
    cols = squares_x - 1  # inner-corner column count

    # Pairwise pixel-distance vs known physical-distance gives ppi estimates.
    # Median is robust to perspective outliers.
    ppi_estimates = []
    for i in range(corners_found):
        for j in range(i + 1, corners_found):
            id_a, id_b = int(c_ids[i][0]), int(c_ids[j][0])
            row_a, col_a = divmod(id_a, cols)
            row_b, col_b = divmod(id_b, cols)
            dx_in = abs(col_a - col_b) * square_size_in
            dy_in = abs(row_a - row_b) * square_size_in
            dist_in = math.hypot(dx_in, dy_in)
            if dist_in < square_size_in:
                continue  # too close → noisy
            pa, pb = c_corners[i][0], c_corners[j][0]
            dist_px = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
            ppi_estimates.append(dist_px / dist_in)

    if not ppi_estimates:
        return CharucoResult(
            detected=False, pixels_per_inch=None, ppi_std_dev=None, ppi_cv=None,
            quality="no_distance_pairs", markers_found=markers_found,
            markers_expected=total_markers_expected, corners_found=corners_found,
            corners_expected=total_corners_expected, distortion="unknown",
            distortion_ratio=None, image_width_px=w, image_height_px=h,
            board_pixel_bbox=None, notes="all detected corners were within one square of each other",
        )

    ppi_arr = np.array(ppi_estimates)
    ppi_median = float(np.median(ppi_arr))
    ppi_std = float(np.std(ppi_arr))
    ppi_cv = ppi_std / ppi_median if ppi_median > 0 else None

    # Quality buckets — same thresholds as detect_charuco.py for continuity.
    quality_excellent = corners_found >= 0.63 * total_corners_expected and (ppi_cv or 1) < 0.05
    quality_good = corners_found >= 0.32 * total_corners_expected and (ppi_cv or 1) < 0.10
    quality_poor = corners_found >= 0.13 * total_corners_expected
    if quality_excellent:
        quality = "excellent"
    elif quality_good:
        quality = "good"
    elif quality_poor:
        quality = "poor"
    else:
        quality = "marginal"

    # Perspective distortion estimate via low-vs-high-quartile ppi spread.
    distortion_ratio = None
    distortion = "unknown"
    if len(ppi_estimates) > 10:
        sorted_ppi = sorted(ppi_estimates)
        q = max(1, len(sorted_ppi) // 4)
        low = float(np.mean(sorted_ppi[:q]))
        high = float(np.mean(sorted_ppi[-q:]))
        distortion_ratio = high / low if low > 0 else None
        if distortion_ratio is None:
            distortion = "unknown"
        elif distortion_ratio < 1.05:
            distortion = "none"
        elif distortion_ratio < 1.15:
            distortion = "slight"
        elif distortion_ratio < 1.30:
            distortion = "moderate"
        else:
            distortion = "severe"

    # Board pixel bbox helps the vision call know where the board is so it
    # can ignore that region when reasoning about the donation.
    pts = np.array([c[0] for c in c_corners], dtype=np.float32)
    bbox = [int(pts[:, 0].min()), int(pts[:, 1].min()),
            int(pts[:, 0].max()), int(pts[:, 1].max())]

    return CharucoResult(
        detected=True,
        pixels_per_inch=round(ppi_median, 3),
        ppi_std_dev=round(ppi_std, 3),
        ppi_cv=round(ppi_cv, 4) if ppi_cv is not None else None,
        quality=quality,
        markers_found=markers_found,
        markers_expected=total_markers_expected,
        corners_found=corners_found,
        corners_expected=total_corners_expected,
        distortion=distortion,
        distortion_ratio=round(distortion_ratio, 3) if distortion_ratio else None,
        image_width_px=w,
        image_height_px=h,
        board_pixel_bbox=bbox,
        notes="",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", help="path to JPEG/PNG")
    ap.add_argument("--squares-x", type=int, default=DEFAULTS["squares_x"])
    ap.add_argument("--squares-y", type=int, default=DEFAULTS["squares_y"])
    ap.add_argument("--square-size-in", type=float, default=DEFAULTS["square_size_in"])
    ap.add_argument("--dictionary", default=DEFAULTS["dictionary"])
    args = ap.parse_args()

    res = analyze(
        args.image,
        squares_x=args.squares_x,
        squares_y=args.squares_y,
        square_size_in=args.square_size_in,
        dictionary_name=args.dictionary,
    )
    print(json.dumps(res.to_dict(), indent=2))
    sys.exit(0 if res.detected else 2)


if __name__ == "__main__":
    main()
