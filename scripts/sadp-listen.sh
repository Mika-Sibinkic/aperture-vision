#!/usr/bin/env bash
# Aperture — find Hikvision cameras via SADP broadcast discovery.
#
# Listens on UDP 37020 for 60s for SADP heartbeat packets AND sends an
# active probe to trigger any Hikvision device on the L2 segment to reply.
# Finds cameras regardless of subnet, DHCP state, or firewall rules.
#
# Usage:  sudo ./scripts/sadp-listen.sh
# Needs sudo because binding UDP 37020 requires privileged port access on Mac.
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  exec sudo -E "$0" "$@"
fi

python3 - <<'PY'
import socket, time, uuid

# Sender for active probe
sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

# Receiver for broadcasts + replies
receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
receiver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    receiver.setsockopt(socket.SOL_SOCKET, 0x0200, 1)  # SO_REUSEPORT on macOS
except OSError:
    pass
receiver.bind(('', 37020))
receiver.settimeout(1.0)

# Active probe — provokes replies from any Hikvision device on the L2 segment
probe = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<Probe><Uuid>' + str(uuid.uuid4()).upper() + '</Uuid>'
    '<Types>inquiry</Types></Probe>'
).encode()
for dest in [('239.255.255.250', 37020), ('255.255.255.255', 37020)]:
    try:
        sender.sendto(probe, dest)
    except OSError as e:
        print(f'(probe to {dest[0]} failed: {e})')

print('Listening 60s on UDP 37020 (Hikvision SADP)…\n')
seen = {}
end = time.time() + 60
while time.time() < end:
    try:
        data, addr = receiver.recvfrom(8192)
    except socket.timeout:
        continue
    text = data[:400].decode('utf-8', errors='replace')
    key = addr[0]
    if key not in seen:
        seen[key] = text
        print(f'▶ DEVICE {addr[0]}:{addr[1]}')
        print(f'  {text}\n')

print(f'\n=== done. {len(seen)} unique device(s) found ===')
for ip in seen:
    print(f'  {ip}')
PY
