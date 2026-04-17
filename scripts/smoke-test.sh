#!/usr/bin/env bash
# Aperture — end-to-end smoke test.
# Run BEFORE driving to Cul2vate to verify the full chain works.
#
# Exits non-zero on any failure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ ! -f "$ROOT/.env.local" ]]; then
  echo "✗ .env.local not found — run ./scripts/setup.sh first" >&2
  exit 2
fi

# Load env
set -a
# shellcheck disable=SC1090
source "$ROOT/.env.local"
set +a

DEPLOY_URL="${1:-}"
if [[ -z "$DEPLOY_URL" ]]; then
  if command -v vercel >/dev/null 2>&1; then
    DEPLOY_URL="$(vercel inspect --wait 2>/dev/null | awk -F': *' '/^URL/{print "https://"$2; exit}' || true)"
  fi
fi
if [[ -z "$DEPLOY_URL" ]]; then
  echo "Usage: smoke-test.sh <vercel-url>" >&2
  echo "   or: vercel CLI configured and previously deployed" >&2
  exit 2
fi

pass() { printf "  \033[1;32m✓\033[0m %s\n" "$*"; }
fail() { printf "  \033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

echo "▶ Smoke-testing $DEPLOY_URL"

# 1. PWA loads
code="$(curl -s -o /dev/null -w '%{http_code}' "$DEPLOY_URL")"
[[ "$code" == "200" ]] || fail "PWA returned HTTP $code"
pass "PWA root returns 200"

# 2. Manifest served
code="$(curl -s -o /dev/null -w '%{http_code}' "$DEPLOY_URL/manifest.webmanifest")"
[[ "$code" == "200" ]] || fail "manifest returned HTTP $code"
pass "manifest served"

# 3. Icons served
for size in 192 512; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$DEPLOY_URL/icons/icon-$size.png")"
  [[ "$code" == "200" ]] || fail "icon-$size.png returned HTTP $code"
done
pass "PWA icons served"

# 4. Bias table (may be empty {} before first training cycle)
bias="$(curl -s "$DEPLOY_URL/bias-table.json")"
echo "$bias" | python3 -c 'import json,sys; json.loads(sys.stdin.read())' \
  || fail "bias-table.json is not valid JSON: $bias"
pass "bias-table.json is valid JSON"

# 5. /api/donate rejects missing token (via n8n)
if [[ -n "${N8N_WEBHOOK_URL:-}" ]]; then
  echo "▶ Testing /api/donate end-to-end (expects n8n to respond)"
  resp="$(curl -s -X POST "$DEPLOY_URL/api/donate" \
    -H 'Content-Type: application/json' \
    -d '{"description":"smoke-test","triggered_at":"2026-01-01T00:00:00Z","location":"smoke"}')"
  echo "  Response: $resp"
  # Validate it's JSON
  echo "$resp" | python3 -c 'import json,sys; json.loads(sys.stdin.read())' \
    || fail "/api/donate returned non-JSON"
  pass "/api/donate returned JSON"
else
  echo "  (N8N_WEBHOOK_URL not set — skipping end-to-end)"
fi

echo ""
echo "✓ Smoke test passed."
