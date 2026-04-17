# Aperture Mac Bridge — interim/demo bridge that runs on Mika's Mac.
#
# Purpose: gives the n8n workflow the SAME interface it expects in production
# (the Dell-hosted bridge), so we can demo tonight from the Mac without
# changing the workflow. When the permanent bridge comes online (Hik-Connect
# on Dell, or mini-PC at Cul2vate), the only thing that changes is the URL
# the n8n env points at — same /snapshot, /snapshot_with_scale, /healthz.
#
# Difference from bridge.py:
#   - Talks to the camera via digest auth at localhost:8888 (the socat bridge
#     to the camera's IPv6 link-local) instead of Hik-Connect cloud
#   - Same response shape, same endpoints, same bearer-token auth
#
# Usage:
#   pip install fastapi uvicorn requests opencv-python-headless pytesseract numpy
#   brew install tesseract                                # for scale OCR (optional)
#   export CAM_PASS='<your camera password>'
#   export BRIDGE_TOKEN=$(openssl rand -hex 32)           # save this for n8n
#   python bridge/mac_bridge.py
#
# Then expose to the internet:
#   cloudflared tunnel --url http://localhost:8002
#
# Use the printed trycloudflare URL as HIKVISION_CAMERA_URL in n8n.

from __future__ import annotations

import base64
import logging
import os
import sys
import time
from typing import Optional

import requests
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from requests.auth import HTTPDigestAuth

# ── config ────────────────────────────────────────────────────────────────────
CAM_USER       = os.environ.get("CAM_USER", "admin")
CAM_PASS       = os.environ["CAM_PASS"]
CAM_BASE       = os.environ.get("CAM_BASE", "http://localhost:8888")  # socat bridge
BRIDGE_TOKEN   = os.environ["BRIDGE_TOKEN"]
SNAPSHOT_TTL_S = float(os.environ.get("SNAPSHOT_TTL_S", "0.5"))
LISTEN_PORT    = int(os.environ.get("LISTEN_PORT", "8002"))
SNAPSHOT_PATH  = os.environ.get("SNAPSHOT_PATH", "/ISAPI/Streaming/channels/101/picture")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("aperture-mac-bridge")

_snapshot_cache: tuple[float, bytes] | None = None
_session = requests.Session()
_session.auth = HTTPDigestAuth(CAM_USER, CAM_PASS)


def _fetch_snapshot() -> bytes:
    global _snapshot_cache
    now = time.time()
    if _snapshot_cache and (now - _snapshot_cache[0]) < SNAPSHOT_TTL_S:
        log.info("snapshot: cache hit (%.2fs old)", now - _snapshot_cache[0])
        return _snapshot_cache[1]

    url = CAM_BASE.rstrip("/") + SNAPSHOT_PATH
    r = _session.get(url, timeout=10)
    r.raise_for_status()
    if not r.content.startswith(b"\xff\xd8"):  # JPEG SOI
        raise RuntimeError(f"camera returned non-JPEG ({len(r.content)} bytes, ct={r.headers.get('content-type')})")
    _snapshot_cache = (now, r.content)
    log.info("snapshot: fetched %d bytes", len(r.content))
    return r.content


app = FastAPI(title="Aperture Mac Bridge")


@app.get("/healthz")
def healthz():
    try:
        # Tiny ISAPI ping that doesn't pull video bandwidth
        r = _session.get(CAM_BASE.rstrip("/") + "/ISAPI/System/deviceInfo", timeout=5)
        r.raise_for_status()
        return {"status": "ok", "camera": "reachable"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "degraded", "error": str(e)})


@app.get("/snapshot")
def snapshot(authorization: str = Header(default="")):
    if authorization != f"Bearer {BRIDGE_TOKEN}":
        raise HTTPException(status_code=401, detail="invalid bearer token")
    try:
        return Response(content=_fetch_snapshot(), media_type="image/jpeg")
    except Exception as e:
        log.exception("snapshot upstream failed")
        return JSONResponse(status_code=503, content={"error": "camera fetch failed", "detail": str(e)})


@app.get("/snapshot_with_scale")
def snapshot_with_scale(authorization: str = Header(default="")):
    if authorization != f"Bearer {BRIDGE_TOKEN}":
        raise HTTPException(status_code=401, detail="invalid bearer token")
    try:
        jpeg = _fetch_snapshot()
    except Exception as e:
        log.exception("snapshot upstream failed")
        return JSONResponse(status_code=503, content={"error": "camera fetch failed", "detail": str(e)})

    # Optional scale OCR (works if cv2 + pytesseract are installed AND
    # bridge/scale_roi.json exists from --calibrate run)
    reading_value: Optional[float] = None
    reading_conf = 0.0
    reading_text = ""
    reading_stable = False
    try:
        from scale_ocr import extract_weight
        reading = extract_weight(jpeg)
        reading_value = reading.value_lbs
        reading_conf = reading.confidence
        reading_text = reading.raw_text
        reading_stable = reading.stable
    except Exception as e:
        log.info("scale OCR unavailable (%s) — returning snapshot without it", e)

    return JSONResponse(content={
        "image_b64": base64.b64encode(jpeg).decode("ascii"),
        "image_bytes": len(jpeg),
        "scale_reading_lbs": reading_value,
        "scale_confidence": reading_conf,
        "scale_raw_text": reading_text,
        "scale_stable": reading_stable,
    })


if __name__ == "__main__":
    import uvicorn
    log.info("aperture-mac-bridge: listening on :%d  (camera at %s)", LISTEN_PORT, CAM_BASE)
    log.info("bearer token: %s", BRIDGE_TOKEN[:6] + "..." + BRIDGE_TOKEN[-4:])
    uvicorn.run(app, host="0.0.0.0", port=LISTEN_PORT, log_level="info")
