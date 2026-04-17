# Aperture Bridge — Hik-Connect cloud-relay snapshot service.
#
# Runs on the always-on Dell G7. Receives snapshot pulls from n8n (via Cloudflare
# Tunnel), authenticates to Hikvision's Hik-Connect cloud, fetches a fresh JPEG
# from the camera at Cul2vate (which the camera pushed via outbound HTTPS — no
# port-forward needed), and returns the bytes to n8n.
#
# Design notes:
# - Bearer-token auth on /snapshot (shared secret with n8n)
# - Hik-Connect session cached, refreshed only on 401/expiry
# - 500ms snapshot dedupe cache so back-to-back presses don't double-bill
# - Structured stdout logs (journalctl-friendly)
# - Graceful degradation: returns 503 with diagnostic JSON on upstream failure
#                         so n8n can surface a clear error to the iPad

from __future__ import annotations

import io
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from pyezviz import EzvizClient, EzvizCamera

# ── config ────────────────────────────────────────────────────────────────────
EZVIZ_REGION       = os.environ.get("EZVIZ_REGION", "apiius.ezvizlife.com")  # USA
EZVIZ_ACCOUNT      = os.environ["EZVIZ_ACCOUNT"]
EZVIZ_PASSWORD     = os.environ["EZVIZ_PASSWORD"]
CAMERA_SERIAL      = os.environ["CAMERA_SERIAL"]
BRIDGE_TOKEN       = os.environ["BRIDGE_TOKEN"]
SNAPSHOT_TTL_S     = float(os.environ.get("SNAPSHOT_TTL_S", "0.5"))
LISTEN_PORT        = int(os.environ.get("LISTEN_PORT", "8002"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("aperture-bridge")

# ── ezviz session (lazy + auto-refreshing) ────────────────────────────────────
_client: Optional[EzvizClient] = None
_camera: Optional[EzvizCamera] = None
_snapshot_cache: tuple[float, bytes] | None = None  # (timestamp, jpeg_bytes)


def _login() -> tuple[EzvizClient, EzvizCamera]:
    """Authenticate to Hik-Connect and return a camera handle."""
    log.info("ezviz: authenticating account=%s region=%s", EZVIZ_ACCOUNT, EZVIZ_REGION)
    c = EzvizClient(EZVIZ_ACCOUNT, EZVIZ_PASSWORD, EZVIZ_REGION)
    c.login()
    cam = EzvizCamera(c, CAMERA_SERIAL)
    cam.load()
    log.info("ezviz: ready serial=%s", CAMERA_SERIAL)
    return c, cam


def _ensure_session() -> EzvizCamera:
    global _client, _camera
    if _camera is None:
        _client, _camera = _login()
    return _camera


def _refresh_session():
    """Force re-login on next call (e.g. after a 401)."""
    global _client, _camera
    _client, _camera = None, None


def _fetch_snapshot() -> bytes:
    """Returns a fresh JPEG. Uses a tiny dedupe cache so concurrent presses
    don't hammer Hik-Connect."""
    global _snapshot_cache
    now = time.time()
    if _snapshot_cache and (now - _snapshot_cache[0]) < SNAPSHOT_TTL_S:
        log.info("snapshot: cache hit (%.2fs old)", now - _snapshot_cache[0])
        return _snapshot_cache[1]

    cam = _ensure_session()
    try:
        url = cam.fetch_pic_url()              # pyezviz returns a signed CDN URL
    except Exception as e:                     # pyezviz wraps 401s as PyEzvizError
        log.warning("snapshot: session may be stale (%s) — refreshing", e)
        _refresh_session()
        cam = _ensure_session()
        url = cam.fetch_pic_url()

    import requests                            # lazy import (small cold start win)
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    jpeg = r.content
    _snapshot_cache = (now, jpeg)
    log.info("snapshot: fetched %d bytes", len(jpeg))
    return jpeg


# ── FastAPI app ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _ensure_session()
    except Exception as e:
        log.error("startup: ezviz login failed (%s) — will retry on first request", e)
    yield


app = FastAPI(title="Aperture Bridge", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    """Liveness probe. Cloudflare/uptime monitors hit this."""
    try:
        _ensure_session()
        return {"status": "ok", "camera_serial": CAMERA_SERIAL[:4] + "***"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "error": str(e)},
        )


@app.get("/snapshot")
def snapshot(authorization: str = Header(default="")):
    if authorization != f"Bearer {BRIDGE_TOKEN}":
        raise HTTPException(status_code=401, detail="invalid bearer token")
    try:
        jpeg = _fetch_snapshot()
    except Exception as e:
        log.exception("snapshot: upstream error")
        return JSONResponse(
            status_code=503,
            content={"error": "camera unreachable via Hik-Connect", "detail": str(e)},
        )
    return Response(content=jpeg, media_type="image/jpeg")


@app.get("/snapshot_with_scale")
def snapshot_with_scale(authorization: str = Header(default="")):
    """JSON response bundling the JPEG (base64) with a deterministic scale-LCD
    OCR reading. n8n uses this endpoint so it can log ground-truth alongside
    the model's prediction for every donation.

    Returns:
      { "image_b64": "...", "scale_reading_lbs": 47.3 | null,
        "scale_confidence": 0.91, "scale_raw_text": "47.3 lb" }
    """
    import base64
    if authorization != f"Bearer {BRIDGE_TOKEN}":
        raise HTTPException(status_code=401, detail="invalid bearer token")
    try:
        jpeg = _fetch_snapshot()
    except Exception as e:
        log.exception("snapshot_with_scale: upstream error")
        return JSONResponse(
            status_code=503,
            content={"error": "camera unreachable via Hik-Connect", "detail": str(e)},
        )

    # Local lazy import — keeps /snapshot cold-start fast even if cv2 is missing
    try:
        from scale_ocr import extract_weight
        reading = extract_weight(jpeg)
    except ImportError:
        log.warning("snapshot_with_scale: scale_ocr unavailable — returning image without scale reading")
        reading = None

    payload = {
        "image_b64": base64.b64encode(jpeg).decode("ascii"),
        "image_bytes": len(jpeg),
        "scale_reading_lbs": reading.value_lbs if reading else None,
        "scale_confidence": reading.confidence if reading else 0.0,
        "scale_raw_text": reading.raw_text if reading else "",
        "scale_stable": reading.stable if reading else False,
    }
    return JSONResponse(content=payload)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=LISTEN_PORT, log_level="info")
