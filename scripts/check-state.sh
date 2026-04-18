#!/usr/bin/env bash
# Aperture — one-shot live state audit.
#
# Reports: Vercel PWA, n8n workflow + fetch URL, Dell bridge health, n8n
# webhook endpoint, last 5 executions. Non-zero exit only if critical things
# are down.
#
# Run from framework root with N8N_API_KEY loaded:
#   source .env
#   cd "Active Projects/Branch Cam Testing/aperture"
#   bash scripts/check-state.sh
set -u

VERCEL_URL="https://<vercel-app-host>"
N8N_BASE="${N8N_BASE_URL:-https://<n8n-host>/api/v1}"
N8N_WORKFLOW_ID="<n8n-workflow-id>"
N8N_WEBHOOK_URL="https://<n8n-host>/webhook/aperture-donate"
DELL_BRIDGE_URL="https://bridge.example.com"

G=$'\033[1;32m'; Y=$'\033[1;33m'; R=$'\033[1;31m'; B=$'\033[1;34m'; N=$'\033[0m'
say()  { printf "\n${B}▶ %s${N}\n" "$*"; }
pass() { printf "  ${G}✓${N} %s\n" "$*"; }
warn() { printf "  ${Y}?${N} %s\n" "$*"; }
fail() { printf "  ${R}✗${N} %s\n" "$*"; }

CRITICAL_FAIL=0

say "1. Vercel PWA ($VERCEL_URL)"
code=$(curl -sS -o /tmp/_aperture_html -w "%{http_code}" --max-time 10 "$VERCEL_URL" 2>/dev/null)
code="${code:0:3}"; [[ -z "$code" ]] && code="000"
if [[ "$code" == "200" ]] && grep -q "Log Donation" /tmp/_aperture_html 2>/dev/null; then
  pass "PWA serving (200, UI markup present)"
else
  fail "PWA HTTP $code"; CRITICAL_FAIL=1
fi
rm -f /tmp/_aperture_html

say "2. n8n API reachability"
if [[ -z "${N8N_API_KEY:-}" ]]; then
  fail "N8N_API_KEY env not set. Did you 'source .env' from framework root?"
  CRITICAL_FAIL=1
else
  code=$(curl -sS -o /tmp/_wf -w "%{http_code}" --max-time 10 \
    -H "X-N8N-API-KEY: $N8N_API_KEY" "$N8N_BASE/workflows/$N8N_WORKFLOW_ID")
  if [[ "$code" == "200" ]]; then
    name=$(python3 -c "import json; print(json.load(open('/tmp/_wf')).get('name'))" 2>/dev/null)
    active=$(python3 -c "import json; print(json.load(open('/tmp/_wf')).get('active'))" 2>/dev/null)
    url=$(python3 -c "
import json
wf = json.load(open('/tmp/_wf'))
fs = next((n for n in wf['nodes'] if n['name']=='Fetch snapshot + scale OCR (via Bridge)'), None)
print(fs['parameters']['url'] if fs else 'MISSING')" 2>/dev/null)
    pass "workflow=$name active=$active"
    case "$url" in
      *bridge.example.com*)
        pass "fetch URL points at Dell bridge → migration complete" ;;
      *trycloudflare.com*)
        warn "fetch URL still points at Mac Quick Tunnel → migration pending" ;;
      *) warn "fetch URL: $url" ;;
    esac
  else
    fail "n8n API HTTP $code"; CRITICAL_FAIL=1
  fi
fi
rm -f /tmp/_wf

say "3. Dell G7 bridge ($DELL_BRIDGE_URL)"
code=$(curl -sS -o /tmp/_bridge -w "%{http_code}" --max-time 10 "$DELL_BRIDGE_URL/healthz" 2>/dev/null)
code="${code:0:3}"
[[ -z "$code" ]] && code="000"
case "$code" in
  200) pass "bridge healthy: $(cat /tmp/_bridge)" ;;
  502|503)
    body=$(cat /tmp/_bridge 2>/dev/null | head -c 200)
    warn "bridge $code (ingress up, service or camera not ready): $body" ;;
  404) warn "bridge $code — Cloudflare ingress rule probably missing" ;;
  000) warn "bridge unreachable — Dell offline, tunnel down, or DNS not propagated" ;;
  *)   warn "bridge unexpected HTTP $code" ;;
esac
rm -f /tmp/_bridge

say "4. n8n webhook endpoint"
code=$(curl -sS -o /tmp/_wh -w "%{http_code}" --max-time 10 -X POST "$N8N_WEBHOOK_URL" \
  -H "content-type: application/json" \
  -H "x-aperture-token: wrong-token-on-purpose" \
  -d '{"probe":true}' 2>/dev/null)
code="${code:0:3}"; [[ -z "$code" ]] && code="000"
if [[ "$code" == "200" ]] && grep -q "invalid token" /tmp/_wh 2>/dev/null; then
  pass "webhook accepting POSTs, token-verify branch fires"
elif [[ "$code" == "200" ]]; then
  warn "webhook 200 but body unexpected: $(cat /tmp/_wh | head -c 120)"
else
  fail "webhook HTTP $code"; CRITICAL_FAIL=1
fi
rm -f /tmp/_wh

say "5. Recent n8n executions (last 5)"
if [[ -n "${N8N_API_KEY:-}" ]]; then
  curl -sS --max-time 10 \
    -H "X-N8N-API-KEY: $N8N_API_KEY" \
    "$N8N_BASE/executions?workflowId=$N8N_WORKFLOW_ID&limit=5" \
    -o /tmp/_exec 2>/dev/null
  python3 - <<'PY'
import json
try:
    d = json.load(open('/tmp/_exec'))
    rows = d.get('data', [])
    if not rows:
        print("  (no executions yet)")
    for e in rows:
        status = e.get("status", "?")
        symbol = "✓" if status == "success" else ("✗" if status == "error" else "?")
        started = e.get("startedAt", "?")[:19]
        print(f"  {symbol}  {e['id']:>5}  {started}  {status}  mode={e.get('mode','?')}")
except Exception as ex:
    print(f"  (exec list unreadable: {ex})")
PY
else
  warn "skipped — N8N_API_KEY unavailable"
fi
rm -f /tmp/_exec

say "Summary"
if [[ "$CRITICAL_FAIL" == "0" ]]; then
  pass "no critical components down"
  echo ""
  echo "  Read ${B}NEXT-STEPS.md${N} for the current blocking item."
  exit 0
else
  fail "at least one critical component is down — see red rows above"
  exit 1
fi
