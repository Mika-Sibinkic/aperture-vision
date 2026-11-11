# Aperture: Docker quickstart for the camera bridge

Five steps to run the camera bridge and the demo harness on one Docker host: clone
the repo, fill 5 secrets, `docker compose up`.

This is the optional bridge path. The Cul2vate install uses the iPad LAN pull and no
on-site computer (`camera-access/ipad/README.md`). This compose file runs
`bridge/bridge.py`, the Hik-Connect variant, and Hik-Connect cloud pull did not work
for the Cul2vate camera (CHANGELOG, 2026-07-22).

## Prerequisites

- Docker 20.10+ with the `compose` plugin
- A Hikvision (or compatible Hik-Connect) IP camera bound to a Hik-Connect
  account, OR a directly-RTSP-reachable camera (then the bridge gets
  replaced with an RTSP grabber; out of scope for this quickstart)
- Outbound HTTPS reachability for OpenAI vision (or local-inference variant)

## 5 steps

```bash
# 1. Clone the repo to the host and cd into it.

# 2. Fill in the 5 ⇨ slots in the env file.
cp deploy/.env.example deploy/.env
$EDITOR deploy/.env

# 3. Build the images (one-time).
docker compose -f deploy/docker-compose.yml build

# 4. Start the bridge.
docker compose -f deploy/docker-compose.yml up -d aperture-bridge

# 5. Verify the bridge is healthy.
curl -fsS http://localhost:8002/healthz
# {"status":"ok","camera_serial":"DH4S***"}
```

## Run the demo (ad-hoc accuracy harness)

```bash
docker compose -f deploy/docker-compose.yml run --rm aperture-demo \
    --provider openai
# writes demo/output/accuracy-report.md + demo/output/residuals.jsonl
```

## What lives where

| Path | Role |
|---|---|
| `bridge/bridge.py` | FastAPI snapshot service (production) |
| `demo/harness.py` | One-shot accuracy validator (developer / pilot) |
| `demo/charuco_preprocessor.py` | Deterministic OpenCV ChArUco math |
| `deploy/Dockerfile.bridge` | Bridge container build |
| `deploy/Dockerfile.demo` | Demo container build |
| `deploy/docker-compose.yml` | Single-host orchestration |
| `deploy/.env.example` | Secrets template (gitignored copy `.env`) |

## Operating notes

- **Logs** go to Docker's json-file driver, capped at 10 MB × 5 files.
- **Healthcheck** runs every 30 s and marks the container unhealthy after 3
  failures. Docker does not restart an unhealthy container on its own;
  `restart: unless-stopped` only restarts it when the process exits.
- **Update** by `git pull && docker compose build && docker compose up -d`.
  Bridge token + camera serial persist (env-file is not rebuilt).
- **Rollback** by `git checkout <prior-commit> && docker compose build && docker compose up -d`.

## Network posture

- Bridge listens on `0.0.0.0:8002` inside the container; map to whatever
  host port your network policy permits (default `8002:8002`).
- For internet-facing exposure: front with a Cloudflare Tunnel or a
  reverse-proxy that adds mTLS. **Do not expose `:8002` publicly without
  a proxy**; the bridge token is a bearer secret, not a per-request
  authenticator.
