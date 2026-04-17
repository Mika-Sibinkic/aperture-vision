#!/usr/bin/env bash
# Aperture — Farmbrite discovery + Aperture-specific setup.
#
# Given an API key, verifies auth, lists existing inventory_types + locations,
# and optionally creates "Aperture Donations" inventory_type. Outputs the
# three env vars n8n needs.
#
# Usage:
#   FARMBRITE_API_KEY=xxxx ./discover-farmbrite-endpoint.sh
#
# Reference: https://developers.farmbrite.com/docs/
set -euo pipefail

: "${FARMBRITE_API_KEY:?set FARMBRITE_API_KEY=…}"
BASE="${FARMBRITE_API_BASE:-https://api.farmbrite.com/v1}"

AUTH=(-H "Authorization: Bearer $FARMBRITE_API_KEY" -H "Accept: application/json")

say()  { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
pass() { printf "  \033[1;32m✓\033[0m %s\n" "$*"; }
fail() { printf "  \033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

command -v jq >/dev/null || fail "jq not installed  (brew install jq)"

# ─── 1. Verify auth ─────────────────────────────────────────────────────────
say "Verifying auth on $BASE"
code="$(curl -s -o /tmp/fb.out -w '%{http_code}' "${AUTH[@]}" "$BASE/inventory_types")"
if [[ "$code" != "200" ]]; then
  echo "  HTTP $code — $(cat /tmp/fb.out | head -c 300)" >&2
  fail "auth failed; double-check API key"
fi
pass "auth OK"

# ─── 2. List inventory_types ────────────────────────────────────────────────
say "Existing inventory_types in your Farmbrite"
BODY="$(curl -s "${AUTH[@]}" "$BASE/inventory_types")"
# Try common envelope shapes.
LIST="$(echo "$BODY" | jq '.inventory_types // .data // .items // .')"
if [[ "$LIST" == "null" || -z "$LIST" ]]; then
  echo "  (empty response — no inventory_types yet)"
else
  echo "$LIST" | jq -r '.[] | "  id=\(.id // .uuid)  name=\"\(.name)\"  unit=\(.unit // "—")"' 2>/dev/null \
    || echo "$LIST" | head -c 600
fi

# ─── 3. Auto-create "Aperture Donations" if none exists with that name ──────
EXISTING_ID="$(echo "$BODY" | jq -r '[.inventory_types // .data // .items // .][0][] | select(.name == "Aperture Donations") | (.id // .uuid)' 2>/dev/null || true)"

if [[ -z "$EXISTING_ID" || "$EXISTING_ID" == "null" ]]; then
  say "No 'Aperture Donations' type found"
  read -r -p "  Create one now? [y/N] " yn
  if [[ "$yn" =~ ^[Yy]$ ]]; then
    CREATE="$(curl -s "${AUTH[@]}" -H "Content-Type: application/json" \
      -d '{"name":"Aperture Donations","unit":"Pounds","description":"Auto-logged incoming food donations weighed by Aperture camera system."}' \
      "$BASE/inventory_types")"
    NEW_ID="$(echo "$CREATE" | jq -r '.id // .uuid // .inventory_type.id // .inventory_type.uuid' 2>/dev/null)"
    if [[ -z "$NEW_ID" || "$NEW_ID" == "null" ]]; then
      echo "  create failed. raw response:" >&2
      echo "$CREATE" | head -c 600 >&2
      fail "could not create inventory_type"
    fi
    pass "created Aperture Donations — id=$NEW_ID"
    INV_ID="$NEW_ID"
  else
    echo "  Pick one of the existing IDs above and set FARMBRITE_INVENTORY_TYPE_ID to it."
    INV_ID="<PICK_FROM_ABOVE>"
  fi
else
  pass "found existing Aperture Donations — id=$EXISTING_ID"
  INV_ID="$EXISTING_ID"
fi

# ─── 4. List locations ──────────────────────────────────────────────────────
say "Existing locations in your Farmbrite"
LOC_CODE="$(curl -s -o /tmp/fb-loc.out -w '%{http_code}' "${AUTH[@]}" "$BASE/locations")"
if [[ "$LOC_CODE" == "200" ]]; then
  LOC_BODY="$(cat /tmp/fb-loc.out)"
  echo "$LOC_BODY" | jq -r '(.locations // .data // .items // .)[] | "  id=\(.id // .uuid)  name=\"\(.name)\""' 2>/dev/null \
    || echo "$LOC_BODY" | head -c 600
else
  echo "  /locations returned HTTP $LOC_CODE — trying /storage_locations…"
  LOC_CODE="$(curl -s -o /tmp/fb-loc.out -w '%{http_code}' "${AUTH[@]}" "$BASE/storage_locations")"
  if [[ "$LOC_CODE" == "200" ]]; then
    cat /tmp/fb-loc.out | jq -r '(.storage_locations // .data // .items // .)[] | "  id=\(.id // .uuid)  name=\"\(.name)\""' 2>/dev/null
  else
    echo "  neither endpoint worked — check Farmbrite UI → Settings → Locations for IDs"
  fi
fi

# ─── 5. Final env block to paste into n8n ───────────────────────────────────
echo ""
echo "────────────────────────────────────────────────────────────"
echo "  Paste these into n8n (Settings → Variables):"
echo ""
echo "    FARMBRITE_API_BASE             = $BASE"
echo "    FARMBRITE_INVENTORY_TYPE_ID    = $INV_ID"
echo "    FARMBRITE_LOCATION_ID          = <pick from list above>"
echo ""
echo "  And the Farmbrite HTTP Header Auth credential in n8n:"
echo "    Name:    Authorization"
echo "    Value:   Bearer $FARMBRITE_API_KEY"
echo "────────────────────────────────────────────────────────────"
