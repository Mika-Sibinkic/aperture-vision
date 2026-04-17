#!/usr/bin/env python3
"""Generate PWA icons using stdlib only (no PIL).

Produces three PNGs in ../public/icons/:
  - icon-192.png          (192x192, PWA manifest)
  - icon-512.png          (512x512, PWA manifest)
  - apple-touch-icon.png  (180x180, iOS home screen)

Design: dark square + concentric aperture ring in accent green + white
center dot. Same palette as the PWA itself.
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

BG = (0x0B, 0x0B, 0x0D, 255)
RING = (0x65, 0xD1, 0x8B, 255)
DOT = (0xFF, 0xFF, 0xFF, 255)


def render(size: int) -> bytes:
    cx = cy = size / 2
    outer = size * 0.46
    inner = size * 0.36
    dot_r = size * 0.08

    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter byte per row
        for x in range(size):
            dx, dy = x - cx, y - cy
            r = math.sqrt(dx * dx + dy * dy)
            if r < dot_r:
                px = DOT
            elif inner <= r <= outer:
                px = RING
            else:
                px = BG
            raw += bytes(px)
    return bytes(raw)


def png_bytes(size: int, raw_rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    idat = zlib.compress(raw_rgba, 9)
    iend = b""
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", iend)


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "public" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    for size, name in [(192, "icon-192.png"), (512, "icon-512.png"), (180, "apple-touch-icon.png")]:
        (out / name).write_bytes(png_bytes(size, render(size)))
        print(f"wrote {out / name} ({size}x{size})")


if __name__ == "__main__":
    main()
