# Deployment state: snapshot at Git migration (2026-06-10)

> **HISTORICAL SNAPSHOT: do not read as current state.** Everything below describes
> 2026-06-10. For what is running right now, and for what can be changed remotely vs.
> on site, read **`docs/OPERATIONS.md`**.

> **Reality check (2026-06-10, per Mika):** current state is NOT an EnterpriseCo-ready deployment. It is an image model with the hope of attaching training data, targeting Cul2vate loading-dock produce measurement. Component statuses below describe plumbing, not validated measurement capability. See docs/BUSINESS.md.

> State: frozen snapshot · Optionality: none (historical record) · Open to Change: no. Live state belongs in checkpoint.md.

## Tracks
| Track | State |
|---|---|
| Cul2vate production (Ellington Ag Center) | PWA + n8n live; **camera bridge DOWN** (Mac bridge killed 2026-04-17; Dell migration paused at Phase 2) |
| EnterpriseCo / the prospect contact enterprise | Met 2026-05-07; static demo + conveyor pivot + paid-pilot posture presented; see docs/deals/enterpriseco/ + docs/sales/ |
| Branch (Antioch) | Pre-Aperture prototype era; not active |

## Live components (as of last checkpoint, 2026-05-19)
| Component | Where | Status |
|---|---|---|
| Vercel PWA + relay | <vercel-app-host> (+ /api/donate) | yes |
| n8n workflow | `<n8n-workflow-id>` @ <n8n-host>, 16 nodes | active |
| Google Sheet log | `<google-sheet-id>` tab Donations | yes |
| Hikvision camera + ChArUco board | Cul2vate site | mounted; unreachable until Dell bridge |
| Mac bridge |  | killed deliberately |
| Farmbrite integration |  | gated on the client contact's API key |

## Blockers (in order)
1. the client contact's reply: camera serial + Farmbrite creds (Gmail thread `<gmail-thread-id>`, sent 2026-04-18)
2. Dell RustDesk session (~25 min, DELL-SESSION.md) for bridge Phases 2+3
3. cloudflared ingress update on Dell (manual root process, NOT systemd; see checkpoint)
4. OPENAI_API_KEY in business-framework/.env for real-vision demo runs

## Secrets
All live values: `SECRETS.local.md` (gitignored); see AGENTS.md convention. Tokens formerly inline in checkpoint.md were redacted at migration; originals preserved in `checkpoint.local.md` and the pre-git tarball (`../aperture-pre-git-backup.tar.gz`).
