#!/usr/bin/env python3
"""
Vision regression test — guards the two failures that silently produce
confident, wrong weights.

  NEGATIVE control  demo/test-images/dock-empty-night-IR.jpg — an ACTUAL frame from
                    the mounted camera (2026-08-01 21:59, night infrared): empty
                    staging zone, cluttered dock around it, monochrome. Ground truth
                    0.0 lb. This is the exact frame on which v0.6 reported
                    "banana box, 50 lbs" — the real failure this suite exists to catch.

  POSITIVE control  a real fruit/veg market photo (fetched from Wikimedia
                    Commons). Must come back with goods and a computed weight.
                    Catches a model biased to answer "empty" for everything —
                    which would silently log 0 lb for every real donation.

  PARROT check      v0.3 embedded a filled-in example JSON in the prompt and the
                    model echoed those exact numbers back (48.4 lb / conf 0.82)
                    on an empty dock. Any answer reusing them fails.

Usage:
    python3 scripts/vision-regression-test.py            # test NIM directly
    python3 scripts/vision-regression-test.py --e2e      # test the live relay
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
RELAY_URL = "https://<vercel-app-host>/api/donate"
def production_model() -> str:
    """Read the model production actually uses, so this suite can never silently test
    a different one (it was pinned to llama-3.2-90b while production ran nemotron)."""
    src = (REPO / "scripts" / "rewire-n8n-ipad-nim.py").read_text()
    m = re.search(r'^NIM_MODEL\s*=\s*"([^"]+)"', src, re.M)
    return m.group(1) if m else "nvidia/nemotron-nano-12b-v2-vl"


MODEL = production_model()
NEGATIVE = REPO / "demo" / "test-images" / "dock-empty-night-IR.jpg"   # REAL frame from the mounted camera, empty zone, night IR
NEGATIVE_OLD = REPO / "demo" / "test-images" / "IMG_0739.JPG"
POSITIVE_TITLE = "File:Obstmarktstand Marburg Firmanei1.jpg"
UA = {"User-Agent": "aperture-vision-regression/1.0 (owner@example.com)"}
PARROT_VALUES = {"weight_lbs": 48.4, "confidence": 0.82, "pixels_per_inch": 2.3,
                 "estimated_volume_cu_in": 1728}


def nim_key() -> str:
    secrets = REPO / "SECRETS.local.md"
    if not secrets.exists():
        sys.exit("ERROR: SECRETS.local.md not found (gitignored; must exist locally).")
    m = re.search(r"nvapi-[A-Za-z0-9_-]+", secrets.read_text())
    if not m:
        sys.exit("ERROR: no NVIDIA NIM key (nvapi-...) in SECRETS.local.md.")
    return m.group(0)


def system_prompt() -> str:
    text = (REPO / "prompts" / "weight-estimation.md").read_text()
    m = re.search(r"^## SYSTEM PROMPT\s*\n(.*?)\n## END SYSTEM PROMPT", text, re.S | re.M)
    if not m:
        sys.exit("ERROR: SYSTEM PROMPT block missing from prompts/weight-estimation.md")
    return m.group(1).strip()


def shrink(src: Path, max_px: int = 1600) -> bytes:
    out = Path(tempfile.gettempdir()) / f"aperture-rt-{src.stem}.jpg"
    subprocess.run(["sips", "-Z", str(max_px), str(src), "--out", str(out)],
                   capture_output=True, check=False)
    return out.read_bytes() if out.exists() else src.read_bytes()


def fetch_positive() -> Path | None:
    dest = Path(tempfile.gettempdir()) / "aperture-positive-control.jpg"
    if dest.exists() and dest.stat().st_size > 10_000:
        return dest
    try:
        url = ("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query", "format": "json", "titles": POSITIVE_TITLE,
            "prop": "imageinfo", "iiprop": "url", "iiurlwidth": "1280"}))
        meta = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40))
        thumb = list(meta["query"]["pages"].values())[0]["imageinfo"][0]["thumburl"]
        dest.write_bytes(urllib.request.urlopen(urllib.request.Request(thumb, headers=UA), timeout=60).read())
        return dest
    except Exception as exc:
        print(f"  ! positive control unavailable ({type(exc).__name__}) — skipping that half")
        return None


def ask_nim(image: bytes, key: str, desc: str = "—") -> dict:
    context = (f"\n\nContext for THIS donation:\ndescription: {desc}\nlocation: Cul2vate, Ellington Ag Center\n"
               "triggered_at: 2026-01-01T00:00:00Z\neval_mode: false\n\nReturn the JSON object now.")
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": system_prompt() + context},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image).decode()}}]}],
        "max_tokens": 800, "temperature": 0, "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(NIM_URL, data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        content = json.load(resp)["choices"][0]["message"]["content"]
    return json.loads(re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip())


def ask_relay(image: bytes, label: str) -> dict:
    # "phantom" cases must send a real item name, since that is the thing under test.
    desc = "Kale" if "phantom" in label else f"REGRESSION TEST — {label}"
    body = json.dumps({"description": desc, "image_b64": base64.b64encode(image).decode(),
                       "triggered_at": "2026-01-01T00:00:00Z", "location": "Cul2vate, Ellington Ag Center",
                       "source": "aperture-regression"}).encode()
    req = urllib.request.Request(RELAY_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        return {"error": exc.read()[:300].decode(errors="replace")}


def parroting(result: dict) -> bool:
    return any(result.get(k) == v for k, v in PARROT_VALUES.items())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--e2e", action="store_true", help="test through the live production relay")
    args = ap.parse_args()

    key = None if args.e2e else nim_key()
    ask = (lambda img, label: ask_relay(img, label)) if args.e2e else (
        lambda img, label: ask_nim(img, key, "Kale" if "phantom" in label else "—"))
    print(f"target: {'live relay ' + RELAY_URL if args.e2e else 'NIM ' + MODEL}\n")

    failures = 0

    print("NEGATIVE control — real dock frame, empty zone (truth 0.0 lb)")
    if not NEGATIVE.exists():
        print("  ! control image missing — cannot run"); failures += 1
    else:
        res = ask(shrink(NEGATIVE), "negative control, empty zone")
        weight, item = res.get("weight_lbs"), res.get("item_type")
        print(f"  -> item={item!r} weight={weight} confidence={res.get('confidence')}")
        if res.get("error"):
            print(f"  ✗ FAIL: {res['error'][:160]}"); failures += 1
        elif parroting(res):
            print("  ✗ FAIL: echoed the prompt's example values (the v0.3 parroting bug)"); failures += 1
        elif item == "empty" or weight in (0, 0.0):
            print("  ✓ PASS")
        else:
            print(f"  ✗ FAIL: invented a donation on an empty dock"); failures += 1

    print("\nPOSITIVE control — real produce photo (must find goods + a weight)")
    positive = fetch_positive()
    if positive:
        res = ask(shrink(positive), "positive control, real produce")
        weight, item = res.get("weight_lbs"), res.get("item_type")
        print(f"  -> item={item!r} weight={weight} confidence={res.get('confidence')}")
        if res.get("error"):
            print(f"  ✗ FAIL: {res['error'][:160]}"); failures += 1
        elif parroting(res):
            print("  ✗ FAIL: echoed the prompt's example values"); failures += 1
        elif item in (None, "empty") or not isinstance(weight, (int, float)) or weight <= 0:
            print("  ✗ FAIL: model is biased to 'empty' — it would log 0 lb for real donations"); failures += 1
        else:
            print("  ✓ PASS")

    # The realistic dock failure: a volunteer types the item, then taps before the
    # load is staged. The description must never conjure goods into an empty zone.
    print("\nPHANTOM-GOODS control — empty zone WITH an item typed (must stay empty)")
    if NEGATIVE.exists():
        res = ask(shrink(NEGATIVE), "phantom control, empty zone, item typed")
        weight, item = res.get("weight_lbs"), res.get("item_type")
        print(f"  -> item={item!r} weight={weight}")
        if item == "empty" or weight in (0, 0.0):
            print("  ✓ PASS")
        else:
            print("  ✗ FAIL: the typed description created goods in an empty zone"); failures += 1

    print("\n" + ("ALL CONTROLS PASSED ✅" if failures == 0 else f"{failures} CONTROL(S) FAILED ❌"))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
