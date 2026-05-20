# Aperture — appliance quickstart

5-step deploy for a fresh on-prem host. This is the plug-and-play
positioning: drop the repo, fill 5 secrets, `docker compose up`.

EnterpriseCo-style production deployment replaces the static-mode bridge with the
conveyor-mode inference service (`docs/EnterpriseCo-conveyor-architecture.md`).
The compose pattern below is the static / Cul2vate-grade version.

## Prerequisites

- Docker 20.10+ with the `compose` plugin
- A Hikvision (or compatible Hik-Connect) IP camera bound to a Hik-Connect
  account, OR a directly-RTSP-reachable camera (then the bridge gets
  replaced with an RTSP grabber — out of scope for this quickstart)
- Outbound HTTPS reachability for OpenAI vision (or local-inference variant)

## 5 steps

```bash
# 1. Clone / sync the repo to the host.
cd aperture/

# 2. Fill in the 5 ⇨ slots in the env file.
cp deploy/.env.example deploy/.env
$EDITOR deploy/.env

# 3. Build the images (one-time, ~3 min).
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

- **Logs** stream to Docker's json-file driver, capped at 10 MB × 5 files.
  Plug into Splunk / DataDog / Loki via the Docker logging driver of choice.
- **Healthcheck** runs every 30 s. Failed health = `restart: unless-stopped`
  bounces the container after the configured retries.
- **Update** by `git pull && docker compose build && docker compose up -d`.
  Bridge token + camera serial persist (env-file is not rebuilt).
- **Rollback** by `git checkout <prior-tag> && docker compose build`. Image
  tags are content-addressed by code state.

## Network posture

- Bridge listens on `0.0.0.0:8002` inside the container; map to whatever
  host port your network policy permits (default `8002:8002`).
- For internet-facing exposure: front with a Cloudflare Tunnel or a
  reverse-proxy that adds mTLS. **Do not expose `:8002` publicly without
  a proxy** — the bridge token is a bearer secret, not a per-request
  authenticator.
- For air-gapped / EnterpriseCo-style deployment: replace the OpenAI-vision worker
  with the on-prem Jetson inference service; no internet egress required.

## When you'd run this vs. the EnterpriseCo architecture

| Need                                     | Use                                |
|------------------------------------------|------------------------------------|
| Pro-bono / pilot / single-press donation | this compose, static mode          |
| Production parcel sortation, <500 ms     | EnterpriseCo conveyor architecture (`docs/EnterpriseCo-conveyor-architecture.md`) |
| Air-gapped enterprise                    | EnterpriseCo architecture, LLM swapped for on-prem CNN |
