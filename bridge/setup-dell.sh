#!/usr/bin/env bash
# Aperture Bridge — one-shot install script for the Dell G7 (or any Debian/Ubuntu host).
#
# What it does:
#   1. Creates a dedicated "aperture" system user (no login, no shell)
#   2. Installs Python deps into an isolated venv at /opt/aperture-bridge/venv
#   3. Copies bridge.py into /opt/aperture-bridge/
#   4. Installs the systemd unit and enables it on boot
#   5. Prompts for /etc/aperture-bridge.env if missing
#   6. Starts the service and tails its log for 5s so you can see it boot
#
# Usage (on the Dell, after `git pull`):
#   cd ~/null-systems-business-framework/Active\ Projects/Branch\ Cam\ Testing/aperture/bridge
#   sudo bash setup-dell.sh
#
# Re-runnable: safe to invoke after a code update. It re-copies bridge.py and
# restarts the service. Env file is only touched if missing.
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  exec sudo -E bash "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR=/opt/aperture-bridge
ENV_FILE=/etc/aperture-bridge.env
UNIT=/etc/systemd/system/aperture-bridge.service

say()  { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
pass() { printf "  \033[1;32m✓\033[0m %s\n" "$*"; }

say "1/6 system user"
if ! id -u aperture >/dev/null 2>&1; then
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin aperture
  pass "created user 'aperture'"
else
  pass "user 'aperture' already exists"
fi

say "2/6 app dir + venv"
mkdir -p "$APP_DIR"
if [[ ! -x "$APP_DIR/venv/bin/python" ]]; then
  apt-get install -y python3-venv python3-pip >/dev/null
  python3 -m venv "$APP_DIR/venv"
  pass "venv created"
fi
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
pass "dependencies installed"

say "3/6 app code"
install -m 0644 -o aperture -g aperture "$SCRIPT_DIR/bridge.py" "$APP_DIR/bridge.py"
chown -R aperture:aperture "$APP_DIR"
pass "bridge.py copied"

say "4/6 systemd unit"
install -m 0644 "$SCRIPT_DIR/systemd/aperture-bridge.service" "$UNIT"
systemctl daemon-reload
pass "unit installed at $UNIT"

say "5/6 environment file"
if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0600 "$SCRIPT_DIR/.env.example" "$ENV_FILE"
  echo ""
  echo "   EDIT THIS FILE NOW:  sudo nano $ENV_FILE"
  echo "   Set: EZVIZ_ACCOUNT, EZVIZ_PASSWORD, CAMERA_SERIAL, BRIDGE_TOKEN"
  echo "   Then re-run this script to start the service."
  exit 0
else
  pass "$ENV_FILE already exists (not overwriting)"
fi

say "6/6 start + verify"
systemctl enable --now aperture-bridge.service
sleep 2
systemctl --no-pager --full status aperture-bridge.service | head -20 || true
echo ""
pass "service enabled at boot. tailing last 5s of logs:"
journalctl -u aperture-bridge.service -n 20 --no-pager
echo ""
echo "Next:"
echo "  1. Verify locally:     curl -s -H 'Authorization: Bearer \$BRIDGE_TOKEN' http://localhost:8002/snapshot -o /tmp/snap.jpg && file /tmp/snap.jpg"
echo "  2. Route via tunnel:   add bridge/cloudflared-route.yml snippet to /etc/cloudflared/config.yml"
echo "  3. Point n8n:          set HIKVISION_CAMERA_URL=https://aperture-bridge.<your-domain>/snapshot"
