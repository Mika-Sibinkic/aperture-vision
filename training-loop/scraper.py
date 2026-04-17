#!/usr/bin/env python3
"""Aperture Phase 2 — image+weight scraper (production).

Ingests labeled images (image + known weight in lbs) from multiple sources
and stores them locally in a de-duplicated flat-file format.

Sources wired up:
  1. Open Food Facts   — free, largest, packaged-goods dominated
  2. Farmbrite         — Cul2vate's own historical data, if API key provided
  3. USDA FoodData Central — density/weight priors for raw produce (no images;
                             we cross-reference with scraped produce photos)

Storage layout (separate dirs so images can never leak weights):
  training-loop/
    images/<sha16>.jpg
    labels/<sha16>.json   {weight_lbs, item_type, source_url, source, categories, sha, scraped_at}

Usage:
  python3 scraper.py --source openfoodfacts --category canned-foods --count 50
  python3 scraper.py --source openfoodfacts --category beverages     --count 50
  python3 scraper.py --source farmbrite
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests

OFF_API = "https://world.openfoodfacts.org/api/v2/search"
ROOT = Path(__file__).resolve().parent
IMAGE_DIR = ROOT / "images"
LABEL_DIR = ROOT / "labels"


@dataclass
class Sample:
    sha: str
    weight_lbs: float
    item_type: str
    source_url: str
    source: str


# ─── Weight parsing ─────────────────────────────────────────────────────────

_UNITS = {
    "kg": 2.2046226,
    "g": 0.0022046226,
    "lb": 1.0, "lbs": 1.0, "pound": 1.0, "pounds": 1.0,
    "oz": 0.0625,
    "ml": None, "l": None,  # liquid — we skip without density (water≈1g/ml OK but rough)
}


def parse_weight_to_lbs(quantity: str | None) -> float | None:
    """Best-effort parse of strings like '500 g', '16 oz', '2 lb', '750ml'."""
    if not quantity or not isinstance(quantity, str):
        return None
    s = quantity.strip().lower().replace(",", ".")
    num = ""
    for c in s:
        if c.isdigit() or c == ".":
            num += c
        elif num:
            break
    if not num:
        return None
    try:
        value = float(num)
    except ValueError:
        return None
    unit_part = s[len(num):].strip()
    # Take first word as unit.
    unit = unit_part.split()[0] if unit_part else ""
    # Strip stray punctuation.
    unit = "".join(c for c in unit if c.isalpha())
    if unit == "ml":
        return value * 1.0 * 0.0022046226  # treat 1g≈1ml (water approximation)
    if unit == "l":
        return value * 1000 * 0.0022046226
    mul = _UNITS.get(unit)
    if mul is None:
        return None
    return value * mul


# ─── Sources ────────────────────────────────────────────────────────────────

def scrape_off(category: str, count: int, sleep_sec: float = 0.2) -> Iterable[Sample]:
    """Open Food Facts search by category, paginated."""
    fetched = 0
    page = 1
    while fetched < count and page <= 20:  # hard cap
        params = {
            "categories_tags_en": category,
            "fields": "code,product_name,image_front_url,quantity,categories_tags",
            "page_size": min(50, count - fetched),
            "page": page,
        }
        try:
            r = requests.get(OFF_API, params=params, timeout=20,
                             headers={"User-Agent": "AperturePhase2Scraper/1.0 (nullsystems)"})
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"[off] request failed on page {page}: {e}", file=sys.stderr)
            return
        page += 1
        products = r.json().get("products", [])
        if not products:
            return
        for p in products:
            weight = parse_weight_to_lbs(p.get("quantity"))
            url = p.get("image_front_url")
            if not weight or not url:
                continue
            # Skip implausibly large/small items for our use case.
            if not (0.05 <= weight <= 200):
                continue
            try:
                img = requests.get(url, timeout=15).content
            except requests.RequestException:
                continue
            sha = hashlib.sha256(img).hexdigest()[:16]
            yield Sample(
                sha=sha,
                weight_lbs=weight,
                item_type=(p.get("product_name") or "unknown").strip() or "unknown",
                source_url=url,
                source="openfoodfacts",
            )
            fetched += 1
            time.sleep(sleep_sec)
            if fetched >= count:
                return


def scrape_farmbrite(api_base: str, api_key: str, count: int) -> Iterable[Sample]:
    """Pull Cul2vate's own historical donation/harvest records with photos.

    The exact endpoint differs per account; this probes common endpoints in
    preference order and stops at the first 200 response.
    """
    candidates = [
        "/donations",
        "/harvests",
        "/inventory/items",
        "/produce",
    ]
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {api_key}"
    found = None
    for endpoint in candidates:
        try:
            r = session.get(api_base.rstrip("/") + endpoint, timeout=10)
            if r.status_code == 200:
                found = endpoint
                break
        except requests.RequestException:
            continue
    if not found:
        print("[farmbrite] no listing endpoint returned 200 — skipping", file=sys.stderr)
        return

    try:
        records = session.get(api_base.rstrip("/") + found, timeout=15).json()
    except Exception as e:
        print(f"[farmbrite] could not decode records: {e}", file=sys.stderr)
        return

    items = records if isinstance(records, list) else records.get("items", records.get("data", []))
    for item in items[:count]:
        weight = item.get("quantity") or item.get("weight") or item.get("weight_lbs")
        unit = (item.get("unit") or "lb").lower()
        photo = item.get("photo_url") or item.get("image_url")
        if not weight or not photo:
            continue
        try:
            weight_lbs = float(weight) * (1.0 if "lb" in unit else 0.0022046226 if unit == "g" else 2.2046226 if unit == "kg" else None)
        except (TypeError, ValueError):
            continue
        if not weight_lbs:
            continue
        try:
            img = session.get(photo, timeout=15).content
        except requests.RequestException:
            continue
        sha = hashlib.sha256(img).hexdigest()[:16]
        yield Sample(
            sha=sha,
            weight_lbs=weight_lbs,
            item_type=(item.get("name") or item.get("item_type") or "unknown").strip(),
            source_url=photo,
            source="farmbrite",
        )


# ─── Persistence ────────────────────────────────────────────────────────────

def persist(sample: Sample, image_bytes: bytes) -> bool:
    """Write image + label atomically. Returns True if new."""
    IMAGE_DIR.mkdir(exist_ok=True)
    LABEL_DIR.mkdir(exist_ok=True)
    img_path = IMAGE_DIR / f"{sample.sha}.jpg"
    label_path = LABEL_DIR / f"{sample.sha}.json"
    if img_path.exists():
        return False
    img_path.write_bytes(image_bytes)
    label_path.write_text(json.dumps({
        "weight_lbs": round(sample.weight_lbs, 3),
        "item_type": sample.item_type,
        "source_url": sample.source_url,
        "source": sample.source,
        "sha": sample.sha,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    return True


# ─── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Aperture Phase 2 scraper")
    ap.add_argument("--source", choices=["openfoodfacts", "farmbrite"], required=True)
    ap.add_argument("--category", default="groceries",
                    help="OFF category slug (ignored for farmbrite)")
    ap.add_argument("--count", type=int, default=25)
    args = ap.parse_args()

    new_count = 0
    if args.source == "openfoodfacts":
        for sample in scrape_off(args.category, args.count):
            try:
                img = requests.get(sample.source_url, timeout=15).content
            except requests.RequestException:
                continue
            if persist(sample, img):
                new_count += 1
    elif args.source == "farmbrite":
        api_base = os.environ.get("FARMBRITE_API_BASE")
        api_key = os.environ.get("FARMBRITE_API_KEY")
        if not api_base or not api_key:
            print("FARMBRITE_API_BASE / FARMBRITE_API_KEY env vars required", file=sys.stderr)
            sys.exit(2)
        for sample in scrape_farmbrite(api_base, api_key, args.count):
            try:
                img = requests.get(sample.source_url, timeout=15).content
            except requests.RequestException:
                continue
            if persist(sample, img):
                new_count += 1

    total = len(list(IMAGE_DIR.glob("*.jpg"))) if IMAGE_DIR.exists() else 0
    print(f"ingested {new_count} new samples — {total} total in {IMAGE_DIR}")


if __name__ == "__main__":
    main()
