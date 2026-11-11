"""The ChArUco preprocessor on the two real dock frames: one good, one honest miss."""
from pathlib import Path

import charuco_preprocessor

IMAGES = Path(__file__).resolve().parent / "test-images"


def test_night_ir_frame_is_calibrated():
    r = charuco_preprocessor.analyze(str(IMAGES / "dock-empty-night-IR.jpg"))
    assert r.detected
    assert r.markers_found == 27
    assert abs(r.pixels_per_inch - 6.164) < 0.05


def test_phone_photo_of_monitor_is_not_detected():
    # IMG_0739 is a phone shot of a VLC window: too few corners survive the moire.
    r = charuco_preprocessor.analyze(str(IMAGES / "IMG_0739.JPG"))
    assert not r.detected
