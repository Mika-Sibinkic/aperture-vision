"""Tesseract-based OCR of the dock platform scale's LCD — automatic
ground truth capture.

The scale is visible in a fixed region of every frame (camera is immobile).
After the initial calibration step that records the LCD's bounding box, we
crop to that region, threshold + deskew, and run Tesseract with the
"digits" model. If a stable numeric reading is extracted, it becomes the
ground_truth for the current donation.

This is the KEY unlock for the learning loop — no human action required
beyond the team's existing practice of placing donations on the scale.

Deterministic (not a vision model call): no stochasticity, no API cost,
no training-data leak risk.

Calibration:
  Run `python -m bridge.scale_ocr --calibrate <sample.jpg>` once after
  the camera is locked into final position. Interactively click the
  four corners of the scale's LCD, and the script writes bbox coords
  to bridge/scale_roi.json. The snapshot handler reads this on load.
"""
from __future__ import annotations

import json
import logging
import pathlib
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

ROI_FILE = pathlib.Path(__file__).parent / "scale_roi.json"


@dataclass
class ScaleReading:
    value_lbs: Optional[float]
    confidence: float          # tesseract mean confidence 0-1
    raw_text: str
    stable: bool               # whether the reading looks like a valid weight


def _read_roi() -> Optional[tuple[int, int, int, int]]:
    if not ROI_FILE.exists():
        return None
    d = json.loads(ROI_FILE.read_text())
    return (d["x"], d["y"], d["w"], d["h"])


def extract_weight(jpeg_bytes: bytes) -> ScaleReading:
    """Returns a ScaleReading. value_lbs is None if OCR couldn't parse
    a plausible weight OR the ROI hasn't been calibrated yet."""
    try:
        import cv2
        import pytesseract
    except ImportError:
        log.warning("scale_ocr: cv2/pytesseract missing — install opencv-python-headless + pytesseract + tesseract-ocr")
        return ScaleReading(None, 0.0, "", False)

    roi = _read_roi()
    if not roi:
        log.info("scale_ocr: ROI not calibrated — skipping (run --calibrate once)")
        return ScaleReading(None, 0.0, "", False)

    # Decode JPEG → ndarray
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return ScaleReading(None, 0.0, "", False)

    x, y, w, h = roi
    crop = img[y:y + h, x:x + w]

    # LCD-friendly preprocessing: grayscale → CLAHE → Otsu threshold → invert if needed
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    _, thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Heuristic: LCD usually dark digits on light background; ensure that orientation
    if np.mean(thresh) < 127:
        thresh = cv2.bitwise_not(thresh)

    # Upscale 2x for better digit recognition on small LCDs
    upscaled = cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    config = "--psm 7 -c tessedit_char_whitelist=0123456789.lbLB"
    data = pytesseract.image_to_data(upscaled, config=config, output_type=pytesseract.Output.DICT)
    text = " ".join(t for t in data["text"] if t.strip())
    confs = [int(c) for c in data["conf"] if c not in ("-1", -1, "")]
    mean_conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0

    # Extract first numeric sequence
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return ScaleReading(None, mean_conf, text, False)
    try:
        value = float(match.group(1))
    except ValueError:
        return ScaleReading(None, mean_conf, text, False)

    # Sanity: scale LCD almost always shows 0 or a weight in lb. Reject
    # extreme values that are likely mis-reads.
    stable = (0 < value < 2000) and mean_conf >= 0.5
    return ScaleReading(value_lbs=value if stable else None, confidence=mean_conf, raw_text=text, stable=stable)


def calibrate(sample_path: str) -> None:
    """Interactive: show the sample, click top-left + bottom-right of the
    LCD, save bbox to scale_roi.json."""
    try:
        import cv2
    except ImportError:
        raise SystemExit("cv2 missing — pip install opencv-python-headless")

    img = cv2.imread(sample_path)
    if img is None:
        raise SystemExit(f"can't read {sample_path}")

    print("Click the top-left corner of the scale LCD, then the bottom-right. Press ESC to abort.")
    clicks: list[tuple[int, int]] = []

    def on_click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            clicks.append((x, y))
            cv2.circle(img, (x, y), 5, (0, 255, 0), -1)
            cv2.imshow("calibrate", img)

    cv2.imshow("calibrate", img)
    cv2.setMouseCallback("calibrate", on_click)
    while len(clicks) < 2:
        if cv2.waitKey(20) == 27:
            raise SystemExit("aborted")
    cv2.destroyAllWindows()

    (x1, y1), (x2, y2) = clicks[0], clicks[1]
    x, y = min(x1, x2), min(y1, y2)
    w, h = abs(x2 - x1), abs(y2 - y1)
    ROI_FILE.write_text(json.dumps({"x": x, "y": y, "w": w, "h": h}))
    print(f"saved bbox to {ROI_FILE}: x={x} y={y} w={w} h={h}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", help="Path to a sample JPEG with the LCD visible; opens interactive click UI")
    ap.add_argument("--test", help="Path to a sample JPEG; runs OCR and prints the reading")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)
    if args.calibrate:
        calibrate(args.calibrate)
    elif args.test:
        reading = extract_weight(pathlib.Path(args.test).read_bytes())
        print(f"value_lbs={reading.value_lbs}  confidence={reading.confidence:.2f}  stable={reading.stable}  raw={reading.raw_text!r}")
    else:
        ap.print_help()
