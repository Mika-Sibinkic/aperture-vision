#!/usr/bin/env bash
# Aperture — one-command bootstrap.
# Run from ~/Desktop/Null\ Systems/business-framework/Active\ Projects/Branch\ Cam\ Testing/aperture/
#
# Idempotent: re-run safely.
#
# Requires: node 20+, npm, python3, vercel CLI (`npm i -g vercel`), openssl.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

say() { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
err() { printf "\n\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }
ok()  { printf "  \033[1;32m✓\033[0m %s\n" "$*"; }

# ── Prereqs ─────────────────────────────────────────────────────────────────
say "Checking prerequisites"
command -v node    >/dev/null || err "node not installed (brew install node)"
command -v npm     >/dev/null || err "npm not installed"
command -v python3 >/dev/null || err "python3 not installed"
command -v openssl >/dev/null || err "openssl not installed"
command -v vercel  >/dev/null || { say "Installing Vercel CLI globally"; npm i -g vercel; }
ok "all prereqs present"

# ── npm deps ────────────────────────────────────────────────────────────────
say "Installing npm dependencies"
if [[ ! -d node_modules ]]; then
  npm install
else
  npm install --no-audit --no-fund
fi
ok "npm install done"

# ── Icons ───────────────────────────────────────────────────────────────────
say "Generating PWA icons"
python3 scripts/generate-icons.py
ok "icons written to public/icons/"

# ── .env.local bootstrap ────────────────────────────────────────────────────
say "Preparing .env.local"
if [[ ! -f .env.local ]]; then
  cp .env.example .env.local
  TOKEN="$(openssl rand -hex 32)"
  # Use awk for cross-platform sed-less edit.
  awk -v t="$TOKEN" '/^APERTURE_SHARED_TOKEN=/{print "APERTURE_SHARED_TOKEN="t; next} {print}' \
    .env.local > .env.local.tmp && mv .env.local.tmp .env.local
  ok ".env.local created with fresh APERTURE_SHARED_TOKEN"
  echo ""
  echo "  Your shared token (save it — you'll paste into n8n too):"
  echo "  $TOKEN"
  echo ""
else
  ok ".env.local already exists — leaving as-is"
fi

# ── Vercel link ─────────────────────────────────────────────────────────────
say "Linking Vercel project"
if [[ ! -f .vercel/project.json ]]; then
  echo "  Follow prompts to link (use existing team, create new project 'aperture')"
  vercel link
else
  ok "already linked"
fi

# ── Vercel env ──────────────────────────────────────────────────────────────
say "Syncing env vars to Vercel production"
if [[ -f .env.local ]]; then
  while IFS='=' read -r key val; do
    [[ "$key" =~ ^#.*$ || -z "$key" || -z "$val" ]] && continue
    # Only push the three vars that belong on Vercel.
    case "$key" in
      N8N_WEBHOOK_URL|APERTURE_SHARED_TOKEN|NEXT_PUBLIC_LOCATION_LABEL)
        printf "%s" "$val" | vercel env add "$key" production --force >/dev/null 2>&1 && ok "$key synced" || {
          printf "%s" "$val" | vercel env add "$key" production >/dev/null 2>&1 && ok "$key synced (first time)" || true
        }
        ;;
    esac
  done < .env.local
fi
echo "  (If N8N_WEBHOOK_URL is empty, come back after activating the n8n workflow and re-run this script.)"

# ── Build locally ───────────────────────────────────────────────────────────
say "Local type-check + build"
npx next build
ok "build succeeded"

# ── Deploy ──────────────────────────────────────────────────────────────────
say "Deploying to Vercel production"
DEPLOY_URL="$(vercel --prod --yes 2>&1 | grep -Eo 'https://[^ ]*vercel.app' | head -1 || true)"
if [[ -z "$DEPLOY_URL" ]]; then
  echo "  (couldn't auto-capture URL — check 'vercel ls' for the deployment)"
else
  ok "deployed: $DEPLOY_URL"
fi

echo ""
echo "────────────────────────────────────────────────"
echo "  Next steps:"
echo "  1. Import n8n/aperture-workflow.json into n8n"
echo "  2. Set n8n env vars (see n8n/README.md)"
echo "  3. Activate workflow, copy Production Webhook URL"
echo "  4. Re-run this script to push N8N_WEBHOOK_URL to Vercel"
echo "  5. On iPad Safari → open $DEPLOY_URL → Add to Home Screen"
echo "  6. Run scripts/smoke-test.sh to verify end-to-end"
echo "────────────────────────────────────────────────"
