#!/usr/bin/env python3
"""
Farmbrite setup + discovery — run this the moment you have the API token.

It figures out the parts nobody documented for us:
  1. WHICH auth header Farmbrite wants (Bearer / raw / X-API-Key / api-key).
     From outside, every variant returns the same "Invalid API Token", so this
     is only answerable with a real token — hence auto-detection here.
  2. What already exists in the Cul2vate account (inventory types, products).
  3. Find-or-create the "Aperture Donations" inventory type to write into.

Verified from outside (2026-07-28), no token needed:
  base https://api.farmbrite.com/v1  — these return 401 (exist), others 404:
  inventory_types, products, crops, animals, contacts, tasks, transactions, orders

Nothing is written unless you pass --create.

Usage:
    export FARMBRITE_API_KEY='...'
    python3 scripts/farmbrite-setup.py              # inspect only
    python3 scripts/farmbrite-setup.py --create     # also create the inventory type
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("FARMBRITE_API_BASE", "https://api.farmbrite.com/v1")
TYPE_NAME = "Aperture Donations"
AUTH_VARIANTS = [
    ("Authorization", "Bearer {t}"),
    ("Authorization", "{t}"),
    ("X-API-Key", "{t}"),
    ("api-key", "{t}"),
    ("X-Api-Token", "{t}"),
]


def call(path: str, header: tuple[str, str], token: str, method: str = "GET", body: dict | None = None):
    name, template = header
    req = urllib.request.Request(
        BASE.rstrip("/") + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={name: template.format(t=token), "Accept": "application/json",
                 **({"Content-Type": "application/json"} if body is not None else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode(errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:300].decode(errors="replace")
    except Exception as exc:  # network, DNS, timeout
        return 0, f"{type(exc).__name__}: {exc}"


def detect_auth(token: str) -> tuple[str, str]:
    print("Detecting the auth header Farmbrite accepts...")
    for header in AUTH_VARIANTS:
        status, _ = call("/inventory_types", header, token)
        label = f"{header[0]}: {header[1].format(t='<token>')}"
        if status == 200:
            print(f"  ✅ {label}")
            return header
        print(f"  ✗  {label}  -> HTTP {status}")
    sys.exit(
        "\nERROR: none of the header formats authenticated.\n"
        "  - Confirm the token is the API token from the Farmbrite developer portal\n"
        "    (Settings > API / developer portal), not the account password.\n"
        "  - Confirm the token was activated after the access request was approved."
    )


def unwrap(payload):
    """Farmbrite may wrap collections; accept the common shapes."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("inventory_types", "products", "data", "items", "results", "records"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def show(header, token, path, label):
    status, payload = call(path, header, token)
    print(f"\n{label}  (GET {path} -> {status})")
    rows = unwrap(payload)
    if status != 200:
        print(f"  {str(payload)[:200]}")
        return []
    if not rows:
        print("  (none yet)")
        return []
    for row in rows[:15]:
        if isinstance(row, dict):
            rid = row.get("id") or row.get("uuid") or row.get("Id")
            name = row.get("name") or row.get("Name") or row.get("title")
            unit = row.get("unit") or row.get("Unit") or "—"
            print(f"  id={rid}  name={name!r}  unit={unit}")
    if len(rows) > 15:
        print(f"  ... and {len(rows) - 15} more")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--create", action="store_true", help="create the Aperture inventory type if absent")
    args = ap.parse_args()

    token = os.environ.get("FARMBRITE_API_KEY", "").strip()
    if not token:
        sys.exit("ERROR: export FARMBRITE_API_KEY='...' first (the token from the Farmbrite developer portal).")

    header = detect_auth(token)

    types = show(header, token, "/inventory_types", "Inventory types in the Cul2vate account")
    show(header, token, "/products", "Products")

    existing = None
    for row in types:
        if isinstance(row, dict) and str(row.get("name") or row.get("Name") or "").strip().lower() == TYPE_NAME.lower():
            existing = row.get("id") or row.get("uuid") or row.get("Id")

    if existing:
        print(f"\n✅ '{TYPE_NAME}' already exists — id={existing}")
    elif args.create:
        status, payload = call("/inventory_types", header, token, "POST", {
            "name": TYPE_NAME, "unit": "Pounds",
            "description": "Incoming food donations weighed automatically by the Aperture camera system.",
        })
        if status not in (200, 201):
            sys.exit(f"\nERROR: create failed (HTTP {status}): {str(payload)[:300]}")
        existing = (payload.get("id") or payload.get("uuid")) if isinstance(payload, dict) else None
        print(f"\n✅ created '{TYPE_NAME}' — id={existing}")
    else:
        print(f"\n'{TYPE_NAME}' does not exist yet. Re-run with --create to make it.")

    print("\n" + "=" * 62)
    print("Paste these back to Claude (or into SECRETS.local.md):")
    print("=" * 62)
    print(f"  FARMBRITE_API_BASE        = {BASE}")
    print(f"  FARMBRITE_AUTH_HEADER     = {header[0]}")
    print(f"  FARMBRITE_AUTH_TEMPLATE   = {header[1]}")
    print(f"  FARMBRITE_INVENTORY_TYPE_ID = {existing or '<create it, then re-run>'}")
    print("  FARMBRITE_API_KEY         = (already in SECRETS.local.md — never paste in chat logs you share)")


if __name__ == "__main__":
    main()
