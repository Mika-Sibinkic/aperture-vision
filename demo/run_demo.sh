#!/usr/bin/env bash
# Aperture demo runner — one-line entrypoint.
#
# Usage:
#   bash demo/run_demo.sh                       # offline: --provider stub, no key, no cost
#   bash demo/run_demo.sh --provider nim        # production prompt + model on NVIDIA NIM (key in SECRETS.local.md)
#   bash demo/run_demo.sh --provider stub --limit 1
#
# Run from the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d "demo/.venv" ]; then
  echo "demo venv missing — creating + installing deps…"
  python3 -m venv demo/.venv
  demo/.venv/bin/pip install --quiet --upgrade pip
  demo/.venv/bin/pip install --quiet -r demo/requirements.txt
fi

# Paid calls only when asked for.
if [ $# -eq 0 ]; then
  set -- --provider stub
fi

demo/.venv/bin/python demo/harness.py "$@"
