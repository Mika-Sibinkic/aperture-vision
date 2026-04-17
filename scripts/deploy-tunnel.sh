#!/usr/bin/env bash
# Aperture — Cloudflare Tunnel bootstrap for the camera endpoint.
#
# Runs on Mika's Mac to create the tunnel + credentials BEFORE the site
# visit, then emits a config.yml and a service-install snippet to run on
# the always-on device at Cul2vate.
#
# Usage:
#   ./deploy-tunnel.sh <tunnel-name> <hostname> <camera-local-ip>
#   e.g.
#   ./deploy-tunnel.sh aperture-cul2vate camera.example.com <camera-ip>
set -euo pipefail

NAME="${1:-aperture-cul2vate}"
HOST="${2:-camera.example.com}"
CAM_IP="${3:-REPLACE_DURING_INSTALL}"

command -v cloudflared >/dev/null || {
  echo "Installing cloudflared…"
  brew install cloudflare/cloudflare/cloudflared
}

if ! cloudflared tunnel info "$NAME" >/dev/null 2>&1; then
  echo "▶ Logging in to Cloudflare (browser will open)"
  cloudflared tunnel login
  echo "▶ Creating tunnel $NAME"
  cloudflared tunnel create "$NAME"
fi

UUID="$(cloudflared tunnel info "$NAME" 2>/dev/null | awk '/ID/{print $NF; exit}')"
CREDS_FILE="$HOME/.cloudflared/$UUID.json"

echo "▶ Routing $HOST → $NAME"
cloudflared tunnel route dns "$NAME" "$HOST"

CONF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/camera-access"
CONF="$CONF_DIR/cloudflared-config.yml"
mkdir -p "$CONF_DIR"
cat > "$CONF" <<EOF
tunnel: $UUID
credentials-file: $CREDS_FILE

ingress:
  - hostname: $HOST
    service: http://$CAM_IP
    originRequest:
      connectTimeout: 10s
      noTLSVerify: true
  - service: http_status:404
EOF

echo ""
echo "─────────────────────────────────────────────────────────"
echo "  Tunnel ready."
echo "  Config written to:      $CONF"
echo "  Credentials at:         $CREDS_FILE"
echo ""
echo "  To run at Cul2vate (on any always-on macOS/Linux device):"
echo ""
echo "    # Copy these two files to the device:"
echo "    scp $CONF $CREDS_FILE pi@cul2vate-box:~/.cloudflared/"
echo ""
echo "    # Then on that device:"
echo "    cloudflared tunnel --config ~/.cloudflared/cloudflared-config.yml run $NAME"
echo ""
echo "  Or install as a service (Linux):"
echo "    sudo cloudflared service install"
echo ""
echo "  Your camera-snapshot URL for n8n:"
echo "    HIKVISION_CAMERA_URL=https://$HOST/ISAPI/Streaming/channels/101/picture"
echo "─────────────────────────────────────────────────────────"
