# Bill of materials: Cul2vate install (reconciled with what's actually bought)

The original audit specced an Axis P3245-LVE at $699 + 48×60 ChArUco. What
actually ended up purchased is listed here. Numbers reflect the real state
as of 2026-04-16.

| Item | Model | Qty | Status | Notes |
|---|---|---|---|---|
| IP Camera | Hikvision AcuSense **<device-serial>** 5MP varifocal | 1 | on-site (in the client contact's storage) | Swap from Axis; $329.95 at B&H. Digest auth. DC12V + PoE input. |
| PoE+ Injector | TP-Link Omada **POE160S** Gigabit | 1 | on-site | 802.3af/at, plug & play. Handles camera power over Cat6. |
| ChArUco Sign | AlphaGraphics Nashville custom, 36×44" Dibond, matte laminate, 6 pre-drilled ¼" holes | 1 | ready for pickup 2026-04-15 | $200 incl TN nonprofit tax exemption. Reference #4550307. |
| Tapcon Screws | ¼" masonry | 6 | on Mika's list | Plus 2-3 spacers per hole for airflow/flatness |
| Hammer Drill |  | 1 | on-site at Cul2vate | the client contact confirmed Mar 24 |
| Masonry Bit | Tapcon-sized | 1 | bring from home | |
| Floor Tape | Yellow | 1 roll | the client contact ordered | For 6×6 staging zone |
| Cat 6 Cable | Outdoor-rated, length TBD at install | 1 | the client contact ordered | Run from WiFi extender → PoE injector → camera |
| Extension Cord |  | 1 | the client contact ordered | For the PoE injector outlet |
| iPad | Existing Cul2vate iPad | 1 | on-site (Mar 31: needs charging) | Any iOS version with Safari + Add-to-Home-Screen |
| WiFi Extender | Existing at Cul2vate | 1 | on-site | Network bridge for camera/iPad |
| Cloudflare Tunnel Host | $40 GL.iNet mini-PC OR Pi Zero 2 W | 1 | to-decide | Only if Option A from camera-access/README.md; verify on-site first |

**Total out of pocket so far:** camera + injector + sign ≈ $560 (approx).
Still within the original $1,454 audit budget.

**Items from the original audit NOT purchased (and fine to skip):**
- Industrial arcade button (iPad handles the press)
- Weatherproof speaker (iPad plays feedback tones in-app if wanted)
- LED frame strip (yellow floor tape is sufficient for v0.1; add later if
  volunteer accuracy is low)
- Raspberry Pi compute + enclosure (compute moved to Vercel + n8n Cloud;
  only a tunnel host is optional)
