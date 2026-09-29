# Camera access: 4 options

n8n Cloud runs off-site. The Hikvision camera lives on Cul2vate's LAN. One of
the four options below has to bridge them. Pick **during** the site visit once
you see what's already at Cul2vate (router model, always-on PC, etc.).

---

## Option A: Cloudflare Tunnel on an existing Cul2vate device (RECOMMENDED)

**When:** Cul2vate has any always-on device on their network (old PC, Mac mini,
an existing Raspberry Pi, or even the WiFi extender if it supports it).

**Pros:** free, HTTPS by default, no inbound firewall rules, auto-reconnects.
**Cons:** requires someone to have `cloudflared` running somewhere.

### Setup (once, from your Mac before you drive up)

```bash
# Install cloudflared locally to create the tunnel
brew install cloudflared
cloudflared tunnel login                 # opens browser, auth to your CF account
cloudflared tunnel create aperture-cul2vate
# Note the Tunnel UUID it prints.

# Route a hostname to the tunnel (replace with a subdomain on a CF-managed zone)
cloudflared tunnel route dns aperture-cul2vate camera.example.com
```

Copy `cloudflared-config.yml.example` to `cloudflared-config.yml`, set the
tunnel UUID + credentials-file path + origin URL (the camera's local IP), then
on the always-on device at Cul2vate:

```bash
# Install cloudflared on the device (macOS, Linux, Windows, Docker, any)
# Copy the tunnel credentials JSON + the config.yml onto it.
cloudflared tunnel --config ~/.cloudflared/config.yml run aperture-cul2vate
```

### Resulting camera URL (put in n8n env)

```
HIKVISION_CAMERA_URL=https://camera.example.com/ISAPI/Streaming/channels/101/picture
```

Digest auth credentials sit in the n8n HTTP Request node.

---

## Option B: Hik-Connect cloud + ISAPI proxy

**When:** no always-on device; camera has internet; the client contact has admin on the
Hikvision app/portal.

**Pros:** uses Hikvision's own cloud. No extra device.
**Cons:** Hik-Connect's public API for snapshot retrieval is thin; often
requires their partner portal auth. **Verify during install that this actually
works for your specific camera firmware before committing.**

Steps:
1. In the Hikvision iVMS-4200 app (or camera web UI) → Network → Platform
   Access → enable **Hik-Connect** and register the device.
2. Get the device serial + verification code.
3. In n8n, replace the "Fetch camera snapshot" node with the Hik-Connect API
   call (Cloudflare Workers proxy if needed).

---

## Option C: Camera-initiated HTTP push

**When:** you want zero inbound exposure.

**How:** configure the Hikvision to POST a snapshot to an n8n webhook when an
alarm fires. The alarm trigger is the iPad button, but the iPad can't reach
the camera directly without a tunnel either… so this only works in combination
with A or D.

Keep in your back pocket as a **secondary trigger path** (e.g., weekly
calibration auto-shots).

Camera web UI → Event → Basic Event → Motion/Alarm → Linkage → HTTP → paste
n8n webhook URL.

---

## Option D: Self-host n8n on the same LAN as the camera

**When:** you decide the on-site device should run n8n itself (not just a
tunnel). This contradicts the "no Pi" pivot, but it IS the simplest to debug
and has zero cloud-round-trip latency.

**Setup:** small mini-PC ($40 GL.iNet router, $75 Beelink mini, Raspberry Pi 4
you may already have from earlier) runs Docker + n8n. Camera reachable by LAN
IP. Vercel `N8N_WEBHOOK_URL` points at `https://<your-tunnel>.example.com`
(you still need a tunnel for Vercel → on-prem n8n, but only for the public
webhook, not the camera).

---

## Decision matrix (fill during site visit)

| Question | Answer |
|---|---|
| Is there a Windows/Mac/Linux device at Cul2vate that stays on 24/7? | |
| Is Hik-Connect already enabled on the camera? | |
| What's the camera's LAN IP after Cat6 is run? | |
| What's the WiFi extender's mgmt IP? | |
| Does the router allow LAN→WAN outbound 443? | |

The recommended default if all unknowns: **Option A using a $40 mini PC you
bring with you pre-flashed**. Set it up on your kitchen table before the
drive. On arrival: plug into power + Ethernet to the extender. Done.
