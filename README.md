# Aperture

Null Systems' AI donation-weighing camera. This repo is the deployment for
Cul2vate Nashville at the Ellington Ag Center loading dock.

## Architecture (one screen)

```
 ┌────────────┐    HTTPS POST    ┌──────────────┐
 │  iPad PWA  │ ───────────────▶ │ Vercel relay │
 │ (Safari/   │                  │ /api/donate  │
 │  home scr) │ ◀─────────────── └──────┬───────┘
 └────────────┘    JSON result          │ HTTPS POST (+ shared token)
                                        ▼
 ┌─────────────────────────────────────────────┐
 │ n8n Cloud — Aperture workflow               │
 │  1. Verify token                            │
 │  2. Fetch snapshot from Hikvision camera    │
 │     (via Cloudflare Tunnel — see            │
 │     camera-access/README.md)                │
 │  3. Vision model → JSON (ChArUco-calibrated │
 │     weight estimate, see prompts/…)         │
 │  4. POST to Farmbrite API                   │
 │  5. Respond with weight + IDs               │
 └─────────────────────────────────────────────┘
```

The iPad **never touches the camera directly** — that would drag us into
Safari mixed-content hell. All camera I/O stays in n8n. The iPad is a dumb
button + text box + result screen.

## What's in here

```
aperture/
├── app/                         # Next.js 16 App Router (the PWA)
│   ├── page.tsx                 # big-button UI
│   ├── layout.tsx               # PWA manifest hookup, iOS meta
│   ├── globals.css              # dark high-contrast outdoor styling
│   └── api/donate/route.ts      # Vercel serverless relay
├── public/
│   ├── manifest.webmanifest     # Add-to-Home-Screen manifest
│   └── icons/                   # ⇨ generate 192/512 PNGs before deploy
├── n8n/
│   ├── aperture-workflow.json   # import into n8n
│   └── README.md                # n8n setup (credentials + env vars)
├── camera-access/
│   ├── README.md                # 4 options for getting snapshots to n8n
│   └── cloudflared-config.yml.example
├── prompts/
│   └── weight-estimation.md     # versioned vision prompt
├── training-loop/               # Phase 2 — RL residual loop (stubs)
│   ├── README.md                # design doc
│   ├── scraper.py               # image+weight scraper stub
│   ├── evaluator.py             # residual computation stub
│   └── requirements.txt
├── docs/
│   ├── DEPLOYMENT.md            # step-by-step for install day
│   └── BOM.md                   # hardware list (what's already bought)
├── .env.example                 # every plug-and-play slot
├── package.json
└── README.md                    # this file
```

## One-command setup

Installs deps, generates icons, creates a shared token, links Vercel, syncs
env vars, builds, and deploys. Idempotent — re-run any time.

```bash
cd aperture
./scripts/setup.sh
```

If you prefer step-by-step:

```bash
cd aperture
npm install
python3 scripts/generate-icons.py      # PNGs → public/icons/
cp .env.example .env.local             # fill slots marked ⇨
npm run dev                            # http://localhost:3000
```

Then deploy:

```bash
npx vercel link                        # one-time: pick team, create "aperture"
npx vercel --prod                      # prints the URL for iPad
```

## Verify before driving to Cul2vate

```bash
./scripts/smoke-test.sh https://aperture-<...>.vercel.app
```

Exits non-zero on any failure. Run it again after n8n is activated to hit the
full chain.

## iPad setup at Cul2vate (60 seconds)

1. Wake the iPad, connect to Cul2vate WiFi.
2. Safari → open the Vercel URL.
3. Share → **Add to Home Screen** → name it "Aperture".
4. Optional: Settings → Display → auto-lock = Never (while on this screen).
5. Done. Tap the new home-screen icon. Standalone full-screen PWA.

## What's unknown — fill in before next chat

See inline `⇨` markers in `.env.example`, `n8n/README.md`, and
`camera-access/README.md`. Concretely, the values I can't know from here:

| Slot | Source |
|---|---|
| Farmbrite API base URL + inventory endpoint + payload shape | the client contact / Farmbrite dashboard |
| Farmbrite API key | Same |
| Hikvision admin user + password | Set during first-boot |
| Hikvision LAN IP | Discovered during install |
| Vision model provider (OpenAI vs Claude vs Gemini) | Your call — OpenAI gpt-4o is the default in the workflow |
| Camera public URL strategy | Pick from `camera-access/README.md` on-site |

## Phase 2 — RL training loop (built, runnable)

Full implementation in `training-loop/`. End-to-end:

```bash
# one-time
pip install -r training-loop/requirements.txt

# run a full cycle (scrape → evaluate → rebuild bias table)
OPENAI_API_KEY=sk-… python3 training-loop/run_cycle.py

# hidden-weight unit test — proves weight never leaks into the prompt
python3 training-loop/test_hidden_weight.py
```

The bias table is written to `public/bias-table.json`. Next `vercel --prod`
publishes it. n8n fetches the live table at each run and applies per-class
weight multipliers before writing to Farmbrite. Clamped to ±20% movement
per cycle (anti-hallucination guardrail).

Run as a daily cron or GitHub Action — see `training-loop/README.md`.
