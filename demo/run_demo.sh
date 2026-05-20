#!/usr/bin/env bash
# Aperture demo runner — one-line entrypoint.
#
# Usage:
#   bash demo/run_demo.sh                # uses OPENAI_API_KEY if set, else --provider stub
#   bash demo/run_demo.sh --provider openai
#   bash demo/run_demo.sh --provider stub --limit 3
#
# Run from `aperture/` repo root.
set -euo pipefail

cd "$(dirname "$0")/.."   # = aperture/

if [ ! -d "demo/.venv" ]; then
  echo "demo venv missing — creating + installing deps…"
  python3 -m venv demo/.venv
  demo/.venv/bin/pip install --quiet --upgrade pip
  demo/.venv/bin/pip install --quiet opencv-contrib-python numpy openai python-dotenv pyyaml requests
fi

# Auto-load OPENAI_API_KEY from the framework .env if it's there.
if [ -f "../../../.env" ]; then
  set -a; source "../../../.env"; set +a
fi

# Default to --provider openai if user didn't pass any args.
if [ $# -eq 0 ]; then
  set -- --provider openai
fi

# If first two args are "--provider openai" and there's no key, fall back to stub.
if [ "${1:-}" = "--provider" ] && [ "${2:-}" = "openai" ] && [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "OPENAI_API_KEY not set — falling back to --provider stub (plumbing test)."
  echo "Set OPENAI_API_KEY in framework .env to run real vision calls."
  set -- --provider stub "${@:3}"
fi

demo/.venv/bin/python demo/harness.py "$@"
