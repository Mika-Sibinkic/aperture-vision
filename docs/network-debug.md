# Aperture — Network Debug Commands

On-site debug commands when a Hikvision camera doesn't show up on the network.

## 1. Ping sweep + ARP dump

Populates the Mac's ARP cache by pinging every host on the /24, then lists
everything that responded.

```bash
(for i in $(seq 1 254); do ping -c 1 -W 50 <lan-prefix>.$i >/dev/null 2>&1 & done; wait) 2>/dev/null
arp -a | grep <lan-prefix> | grep -v incomplete
```

Limit: only shows devices that respond to ICMP and that your Mac has
resolved via ARP. Doesn't find Hikvision cameras that are firewalling ping.

## 2. nmap L2 discovery (more reliable than ping sweep)

```bash
brew install nmap          # one-time
sudo nmap -sn <lan-subnet>
```

`-sn` with a local /24 triggers ARP scanning — finds devices even if they
ignore ICMP. Vendor names print next to each MAC (look for "Hikvision").

## 3. SADP broadcast listener — the nuclear option

Hikvision cameras broadcast SADP discovery packets on UDP 37020 every
~20–30 sec. This listener finds the camera regardless of subnet, DHCP
state, or whether it's responding to ARP.

```bash
sudo python3 -c "
import socket, time
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
try: s.setsockopt(socket.SOL_SOCKET, 0x0200, 1)  # SO_REUSEPORT
except: pass
s.bind(('', 37020))
s.settimeout(60)
print('Listening 60s on UDP 37020 for SADP broadcasts…')
seen = set()
end = time.time() + 60
while time.time() < end:
    try:
        data, addr = s.recvfrom(4096)
        if addr[0] not in seen:
            seen.add(addr[0])
            snippet = data[:200].decode('utf-8', errors='replace')
            print(f'FROM {addr[0]}:{addr[1]}  →  {snippet!r}')
    except socket.timeout:
        break
print('done. unique broadcasters:', list(seen))
"
```

Or just run: `./scripts/sadp-listen.sh`

## 4. Active SADP discovery — ping the segment for Hikvision responses

If the camera isn't broadcasting on its own, provoke a response by
sending the SADP discovery query:

```bash
sudo python3 -c "
import socket, time, uuid
sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
receiver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try: receiver.setsockopt(socket.SOL_SOCKET, 0x0200, 1)
except: pass
receiver.bind(('', 37020))
receiver.settimeout(8)
query = (
  '<?xml version=\"1.0\" encoding=\"utf-8\"?>'
  '<Probe><Uuid>' + str(uuid.uuid4()).upper() + '</Uuid>'
  '<Types>inquiry</Types></Probe>'
).encode()
for dest in [('239.255.255.250', 37020), ('255.255.255.255', 37020)]:
    sender.sendto(query, dest)
print('probe sent; listening 8s…')
seen = set()
end = time.time() + 8
while time.time() < end:
    try:
        data, addr = receiver.recvfrom(4096)
        if addr[0] not in seen:
            seen.add(addr[0])
            print(f'REPLY {addr[0]}:{addr[1]}  →  {data[:400].decode(\"utf-8\", errors=\"replace\")}')
    except socket.timeout:
        break
print('done. replies from:', list(seen))
"
```

If no reply comes back on either listener, the camera isn't communicating
at all — hardware/cable issue, not a network config issue.

## 5. Factory-default IP probe (temporary Mac IP override)

Manually set the Mac's IP to the Hikvision default subnet and try the two
common defaults:

- System Settings → Network → Wi-Fi → Details → TCP/IP
- Configure IPv4: **Manually**
- IP: `<gateway-ip>00`  ·  Mask: `255.255.255.0`  ·  Router: `<gateway-ip>`
- Browser: `http://<camera-ip>`

Repeat with `<host-ip>` / `http://<camera-ip>` for older firmware.

**Revert to DHCP afterward** or you'll lose internet.

## 6. Directly wire Mac to PoE injector LAN IN

Puts the Mac on the same L2 segment as the camera, bypassing any Eero
mesh weirdness. Requires a USB-C → Ethernet adapter.

1. Unplug the short Cat6 from Eero's LAN port (leave it attached to the
   POE160S `LAN IN`).
2. Plug the free end of that Cat6 into the Mac via adapter.
3. Mac should get a link-local or stay on WiFi DHCP — either way, set
   static: `<gateway-ip>00` as in §5.
4. Browse `http://<camera-ip>`.

If the camera answers here but not through the Eero, the Eero extender's
LAN port is isolating wired clients — plug the injector into the **main
Eero** instead of the extender.

## 7. Factory reset the camera

Hikvision bullets have a recessed pinhole on the back labeled RESET.
Hold paperclip in it for **15 seconds** with the camera powered on.
Camera reboots with factory defaults (including DHCP on, password clear).

Use as a last resort — you'll need to re-adjust zoom/focus after.
