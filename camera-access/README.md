# Camera access

n8n Cloud runs off-site. The Hikvision camera lives on Cul2vate's LAN. Something has to
get a frame from one to the other.

## RECOMMENDED: the iPad pulls the frame over the LAN

This is what runs at Cul2vate. At the tap, the on-site iPad pulls a JPEG from the
camera with HTTP digest auth and posts it to the relay. Nothing on the LAN is reachable
from the internet and there is no on-site computer. Setup: `ipad/README.md` and
`ipad/ONSITE-CARD.md`. Why: `../docs/decisions/2026-07-22-ipad-lan-bridge.md`.

Four other routes came first: a Cloudflare Tunnel to the camera, the Hik-Connect cloud,
a camera-initiated HTTP push, and n8n hosted on the LAN. Hik-Connect proved dead for
this camera and the rest need an always-on box. They are in git history:
`git log --all -- camera-access/README.md`.
