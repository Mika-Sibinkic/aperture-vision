#!/usr/bin/env bash
# Aperture — Phase 4 cutover. Patches the live n8n workflow so the
# "Fetch snapshot + scale OCR (via Bridge)" node points at the Dell
# bridge at bridge.example.com. Idempotent.
#
# Preconditions:
#   - N8N_API_KEY + N8N_BASE_URL in env (source .env from framework root)
#   - Dell bridge healthy: curl https://bridge.example.com/healthz = 200
#
# Run:
#   source .env
#   cd "Active Projects/Branch Cam Testing/aperture"
#   bash scripts/patch-n8n-to-dell.sh
set -euo pipefail

WORKFLOW_ID="<n8n-workflow-id>"
DELL_URL="https://bridge.example.com/snapshot_with_scale"
OLD_URL_PATTERN="trycloudflare.com"
VERCEL_URL="https://<vercel-app-host>"

G=$'\033[1;32m'; Y=$'\033[1;33m'; R=$'\033[1;31m'; B=$'\033[1;34m'; N=$'\033[0m'
say()  { printf "\n${B}▶ %s${N}\n" "$*"; }
pass() { printf "  ${G}✓${N} %s\n" "$*"; }
warn() { printf "  ${Y}?${N} %s\n" "$*"; }
die()  { printf "  ${R}✗${N} %s\n" "$*"; exit 1; }

[[ -n "${N8N_API_KEY:-}" ]] || die "N8N_API_KEY not set. source .env from framework root."
[[ -n "${N8N_BASE_URL:-}" ]] || die "N8N_BASE_URL not set."

say "0. Preflight — Dell bridge must be reachable"
code=$(curl -sS -o /tmp/_h -w "%{http_code}" --max-time 10 "https://bridge.example.com/healthz")
if [[ "$code" != "200" ]]; then
  cat /tmp/_h
  die "Dell bridge /healthz returned HTTP $code. Fix bridge before cutting over."
fi
pass "bridge OK: $(cat /tmp/_h)"

say "1. Pull current workflow"
curl -sS --max-time 15 -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$N8N_BASE_URL/workflows/$WORKFLOW_ID" -o /tmp/_wf.json

set +e
python3 - <<PY
import json, sys
wf = json.load(open('/tmp/_wf.json'))
print(f"  workflow={wf['name']!r}  active={wf['active']}  nodes={len(wf['nodes'])}")
fs = next((n for n in wf['nodes'] if n['name']=='Fetch snapshot + scale OCR (via Bridge)'), None)
if not fs:
    print("  FATAL: Fetch snapshot node not found")
    sys.exit(1)
current = fs['parameters'].get('url','')
print(f"  current fetch URL: {current}")
if "bridge.example.com" in current:
    print("  → already on Dell bridge — no-op.")
    sys.exit(77)
if "$OLD_URL_PATTERN" not in current:
    print("  FATAL: current URL doesn't match expected Mac-tunnel pattern. Aborting.")
    sys.exit(1)
PY
rc=$?
set -e
if [[ $rc -eq 77 ]]; then
  pass "already migrated"
  exit 0
elif [[ $rc -ne 0 ]]; then
  exit 1
fi

say "2. Patch fetch URL in local copy"
python3 - <<PY
import json
wf = json.load(open('/tmp/_wf.json'))
fs = next(n for n in wf['nodes'] if n['name']=='Fetch snapshot + scale OCR (via Bridge)')
fs['parameters']['url'] = "$DELL_URL"
for k in ("id","active","createdAt","updatedAt","triggerCount","versionId","tags","shared"):
    wf.pop(k, None)
json.dump(wf, open('/tmp/_wf_patched.json','w'), indent=2)
print(f"  patched URL to: {fs['parameters']['url']}")
PY

say "3. PUT back via API"
code=$(curl -sS -o /tmp/_put -w "%{http_code}" --max-time 20 \
  -X PUT -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  "$N8N_BASE_URL/workflows/$WORKFLOW_ID" \
  --data-binary @/tmp/_wf_patched.json)
if [[ "$code" != "200" ]]; then
  cat /tmp/_put | head -c 500
  die "PUT returned HTTP $code"
fi
pass "workflow updated"

say "4. Verify round-trip"
curl -sS --max-time 10 -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$N8N_BASE_URL/workflows/$WORKFLOW_ID" -o /tmp/_wf_verify.json
python3 - <<PY
import json, sys
wf = json.load(open('/tmp/_wf_verify.json'))
fs = next(n for n in wf['nodes'] if n['name']=='Fetch snapshot + scale OCR (via Bridge)')
url = fs['parameters']['url']
if "bridge.example.com" not in url:
    print(f"  FATAL: URL didn't stick: {url}")
    sys.exit(1)
print(f"  verified: {url}")
print(f"  active={wf['active']}")
PY

say "5. End-to-end preflight via Vercel"
resp=$(curl -sS --max-time 60 -X POST "$VERCEL_URL/api/donate" \
  -H "content-type: application/json" \
  -d "{\"description\":\"post-migration cutover preflight\",\"location\":\"Cul2vate\",\"triggered_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}")
echo "  response: $resp"
if echo "$resp" | grep -qE '"weight_lbs"|"item_type"|"confidence"'; then
  pass "end-to-end success — iPad→Vercel→n8n→Dell→camera→OpenAI→Sheet"
else
  warn "preflight returned unexpected payload — inspect n8n executions"
fi

rm -f /tmp/_wf.json /tmp/_wf_patched.json /tmp/_wf_verify.json /tmp/_put /tmp/_h
say "Cutover complete."
echo ""
echo "  Next: tap the iPad with tomatoes in the crate."
echo "  If anything's off, run:  bash scripts/check-state.sh"
