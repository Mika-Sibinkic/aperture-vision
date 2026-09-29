# Aperture: perceived specification

> Accuracy approach is an open portfolio (SKU lookup, training data, OCR, priors, hybrid); see docs/ACCURACY-ROADMAP.md before extending the vision pipeline. Prompt should eventually emit sku_candidate / label_text / confidence.

**Author:** Claude (Mika's working instance, session 2026-04-17 → 2026-04-18)
**Status:** PERCEIVED: my understanding of the product, not verified against every source.
**Purpose of this file:** give a fresh instance enough context to challenge, correct, and flesh out this spec where I'm wrong, vague, or missing something.

**Read this critically.** If something contradicts what's in the code, `docs/`, Gmail threads, or Mika's memory, the other source wins and this file needs updating. Every claim here should be treated as a hypothesis until verified.

---

## 1. Product identity

- Name: Aperture (Null Systems' product name for the Cul2vate loading-dock camera system)
- Client: Cul2vate (the client contact, Harvest Director, Ellington Ag Center, Nashville TN). Nonprofit that accepts food donations.
- Builder: Mika Sibinkic / Null Systems LLC, a solo AI-augmented consulting practice.
- Legacy folder name: `Active Projects/Branch Cam Testing/`, not renamed for historical reasons.
- Application code root: `Active Projects/Branch Cam Testing/aperture/`
- Live as of: 2026-04-17 demo (tomatoes in a crate scored 0 residual; high-confidence empty-zone result).

## 2. What problem does it solve?

A volunteer at Cul2vate's Ellington Ag Center brings in a food donation, places it in the staging zone at the dock, and taps an iPad. The system autonomously identifies the item, estimates the weight, and logs the donation to a Google Sheet (and eventually to Farmbrite, Cul2vate's inventory system), **without requiring any human in the loop besides the tap**.

The problem it replaces: manual log-and-weigh, which is slow, error-prone, and discourages complete record-keeping.

## 3. End-to-end architecture

```
┌────────────┐    HTTPS POST    ┌──────────────────┐
│  iPad PWA  │ ───────────────▶ │ Vercel relay     │
│ (Safari    │  X-Aperture-Token│ /api/donate      │
│  PWA)      │ ◀─────────────── │ (maxDuration=60) │
└────────────┘    JSON result   └────────┬─────────┘
                                         │ HTTPS POST (+ shared token)
                                         ▼
                    ┌───────────────────────────────────────────────┐
                    │ n8n Cloud (Starter) - workflow <n8n-workflow-id> │
                    │  1. Verify shared token                         │
                    │  2. Fetch snapshot from bridge (+ bridge token) │
                    │  3. Guard: is scale reading in frame?           │
                    │  4. langchain OpenAI GPT-4o vision → JSON       │
                    │  5. Compute residual vs ChArUco calibration    │
                    │  6. Append row to Google Sheet "Donations"      │
                    │  7. [pending] POST to Farmbrite inventory API  │
                    └────────┬──────────────────────────────────────┘
                             │ HTTPS GET /snapshot_with_scale
                             ▼
             ┌────────────────────────────────────────────┐
             │ Aperture bridge (Dell G7 in Nashville)     │
             │ - Cloudflare Tunnel ingress:               │
             │   bridge.example.com       │
             │ - FastAPI on :8002                         │
             │ - pyezviz → Hik-Connect cloud              │
             │ - Optional OpenCV ChArUco preprocessor     │
             │   (v1.1, not yet active)                   │
             └────────┬──────────────────────────────────┘
                      │ Hik-Connect cloud relay (outbound HTTPS only)
                      ▼
             ┌────────────────────────────────────────────┐
             │ Hikvision AcuSense <device-serial> camera       │
             │ at Cul2vate dock - outdoor bullet, 5MP,    │
             │ 2.7-13.5mm zoom lens, 138° max diagonal    │
             │ FOV. ChArUco board (36×44" Dibond, 32×40"  │
             │ pattern, 6" squares) mounted on brick wall │
             │ within FOV for calibration.                │
             └────────────────────────────────────────────┘
```

## 4. Users and usage model

- Primary user: volunteer at the Cul2vate dock. Interaction: place donation, tap iPad PWA, read confirmation. Zero training expected.
- Secondary user: Cul2vate staff reviewing donation log. Interaction: open Google Sheet (and eventually Farmbrite) to see what arrived and when.
- Operator: Mika (Null Systems). Interaction: monitor uptime, respond to failures, iterate on accuracy.
- Hardware minder: the client contact. Interaction: physical camera access at the dock for setup/troubleshooting. Not a daily role.

## 5. Functional requirements

### Must-have (v1)
- [x] iPad PWA installable from Vercel URL, single-button donation trigger
- [x] Shared-token auth from iPad → Vercel → n8n → bridge
- [x] Camera snapshot retrieval (target: ≤3s round-trip)
- [x] Vision-based item identification (produce type)
- [x] Vision-based weight estimation (ChArUco-calibrated)
- [x] JSON-structured vision output (LLM-as-parser with JSON-forced prompt)
- [x] Google Sheet row append per donation
- [x] Always-on backend (Dell G7 + Cloudflare tunnel)
- [ ] Farmbrite inventory write (node stubbed, blocked on the client contact's API creds)
- [ ] Uptime monitor on `/healthz` (post-cutover task)
- [ ] Firmware freeze documentation

### Nice-to-have (v1.1+, in `docs/V2-AGENDA.md`)
- ChArUco OpenCV preprocessor on bridge (+8-15 pp residual accuracy)
- Scale-in-frame OCR for ground-truth weight (`scale_ocr.py` scaffolded)
- Image storage (Vercel Blob or R2) for audit + retraining
- Specialist ensemble vision (5 sub-calls for edge cases, +5-10 pp)
- Learned densities per item/supplier/season (+3-7 pp)
- iPad correction button (redundant ground-truth)

### Out of scope for v1 (per `docs/PRD.md §11-§12`)
- LED-framed staging zone for vision reliability
- Industrial waterproof button (hardware trigger alternative to iPad)
- Status LED + audio feedback loop
- Anomaly detection
- Weekly volume forecasting
- IR night mode

## 6. Non-functional requirements

- Availability: 24/7 uptime; target 99%+ once Dell migration is complete. No SLA with Cul2vate (pro-bono/passion project).
- Latency: iPad tap to confirmation ≤15s typical, ≤60s worst-case (Vercel `maxDuration=60`).
- Reliability: firmware frozen on camera (Hikvision auto-upgrades are risk); n8n workflow snapshot committed for rollback; bridge service self-restarts via systemd.
- Security posture: defense-in-depth with separate shared tokens at iPad→Vercel, Vercel→n8n, n8n→bridge. No secrets in PWA source. Bridge exposed only over HTTPS via Cloudflare Tunnel (no port forwarding at Cul2vate).
- Recoverability: rollback procedure documented in `docs/MIGRATION-RUNBOOK.md §Rollback`. Core artifacts versioned in git.
- Observability (current): n8n execution log; Google Sheet as a de facto audit log. No structured metrics dashboard yet.
- Observability (gap): no uptime monitor on `/healthz`; no alerting on 503. This is a known gap.

## 7. Known fragilities (verified during build)

1. **`pyezviz` is community-maintained.** Pin to `0.2.2.5`; upgrade only with testing.
2. **Hik-Connect register status can drop** on camera power or net events. Auto-recovers in ~30s. Not a bug, a property.
3. **Firmware auto-upgrade must stay disabled** at both camera UI and hik-connect.com dashboard.
4. **Scale OCR needs calibration** before yielding readings; single `--calibrate` run post-deploy.
5. **n8n langchain OpenAI v1.6 silently drops `systemMessage` + `responseFormat`** on Cloud Starter v2.13.3. Mitigation: embed JSON schema in user text. Documented in `.claude/integrations/registry.json → n8n.learned_patterns`.
6. **n8n `httpRequest` typeVersion 5** renders as "Install this node" on Starter plan; use 4.2.
7. **JSON re-import clears `credentials: {}` even when IDs match**: always re-attach after import.

## 8. Dependencies (external systems that can break us)

| System | Criticality | Failure behavior |
|---|---|---|
| Hikvision Hik-Connect cloud | critical (runtime) | camera unreachable via bridge |
| Cloudflare Tunnel + DNS (example.com) | critical (runtime) | bridge unreachable from n8n |
| Vercel (PWA + `/api/donate`) | critical (runtime) | iPad can't submit |
| n8n Cloud Starter (<n8n-host>) | critical (runtime) | workflow can't execute |
| OpenAI API | critical (runtime) | vision analysis fails |
| Google Sheets API | high (runtime) | donation log fails, but execution continues |
| Farmbrite API | low (pending) | not yet wired |
| Cul2vate LAN / Eero | one-time (setup) | needed for Platform Access enable, not runtime |
| Dell G7 power + WSL2 | critical (runtime) | entire bridge stack down |

## 9. Current deployment state (as of 2026-04-18)

- Vercel PWA + relay: live at `https://<vercel-app-host>`
- n8n workflow: active on Starter plan, Bridge node still points at dead trycloudflare URL; cutover pending
- Google Sheet: `<google-sheet-id>`, tab `Donations`, rows flowing
- Camera: physically mounted at Cul2vate, focus locked, ChArUco visible. **Not yet bound to Hik-Connect** (pending serial + Platform Access enable)
- Mac bridge (interim): intentionally killed 2026-04-17 after demo
- Dell bridge: code committed + pushed, not yet installed (pending RustDesk session)
- Hik-Connect account: created + logged in 2026-04-18 ~19:27 CDT, no device bound yet

## 10. Active blockers (ordered by unblocking value)

1. **RustDesk session on Dell** (~25 min, Mika): installs bridge, wires Cloudflare ingress. Unblocks Phase 4.
2. **Camera serial from the client contact** (9 digits): unblocks Hik-Connect binding. Cleanest path: the client contact on next Cul2vate visit reads it from camera UI Basic Information page, also enables Platform Access in the same session.
3. n8n cutover (Phase 4): automated via `scripts/patch-n8n-to-dell.sh`. Refuses to run unless `/healthz`=200. ~90 sec.
4. Farmbrite API creds from the client contact: orthogonal; doesn't block v1 cutover but blocks auto-write to Cul2vate's inventory system.

## 11. Open questions / where this spec may be wrong

These are places where I've been filling in defaults from context; a fresh instance should challenge and verify each:

- **Accuracy target.** What residual % or weight-error tolerance is acceptable to Cul2vate? Demo showed residual ~0 on an empty zone; that's one data point, not a distribution.
- **Donation volume.** Daily? Weekly? Peak concurrency (multiple donors at once)? The current workflow assumes one tap at a time; no queue.
- **Multi-user model.** Do volunteers need individual accounts, or is the iPad's shared token enough forever? No audit-per-user today.
- **Failure UX.** What should the iPad show if the bridge returns 503 or the camera is offline? The PWA's current behavior on error has not been explicitly designed.
- **Offline / degraded mode.** If Hik-Connect is down, does the iPad tap fail loudly or retry silently? Current answer: fails loudly after 60s. Is that acceptable?
- **Long-term ownership.** Post-handoff, who maintains this? The ops runbook (`docs/PRODUCTION-RUNBOOK.md`) assumes Mika stays in the loop. Is there a plan for an eventual Cul2vate-internal operator?
- **Data retention.** Google Sheet grows forever today. Is there a retention policy? A need to archive?
- **Farmbrite write semantics.** If the n8n write to Farmbrite fails but Sheet succeeds, is that acceptable (Sheet is source of truth) or does Farmbrite need to be transactional?
- **Calibration drift.** ChArUco is a static reference, but what if the camera gets bumped or the board is moved? Is there a self-check that flags when calibration no longer matches?
- **Seasonal produce variance.** Density/appearance of "tomatoes" in August vs December may differ enough to affect weight estimation. Is there a retraining cadence planned?
- **Incident response.** If the system breaks at 3am, who gets paged? Currently: no one; this is not a paged service.
- **B&H order receipt** (resolved 2026-04-18): does NOT expose device-unique serial; only SKU-level. Confirmed via screenshots.
- **the client contact's bandwidth.** What's the client contact's availability for a ~15-min on-site session at Cul2vate to enable Platform Access and grab the serial? No firm date yet.

## 12. Files that are load-bearing for this project

| File | Role |
|---|---|
| `ACT.md` | Autonomous action playbook: Q1-Q7 decision tree for any instance |
| `checkpoint.md` | Live state: URLs, tokens, IDs, progress log, Dell preflight |
| `DELL-SESSION.md` | Copy-paste bundle for Mika's RustDesk session |
| `NEXT-STEPS.md` | Blocker-ordered action list (older but still accurate) |
| `SPEC.md` | This file: perceived spec, subject to correction |
| `docs/MIGRATION-RUNBOOK.md` | Full-detail Mac → Dell migration (5 phases) |
| `docs/PRODUCTION-RUNBOOK.md` | Ops guide post-cutover |
| `docs/HIK-CONNECT-SETUP.md` | Camera-side setup steps |
| `docs/V2-AGENDA.md` | Post-v1 backlog (accuracy + features) |
| `docs/PRD.md` | Original PRD |
| `docs/DETERMINISM.md` | Reasoning for JSON-forced prompts + calibration approach |
| `docs/LEARNING-LOOPS.md` | Plan for closing the accuracy learning loop |
| `bridge/bridge.py` | FastAPI + pyezviz bridge code (Dell) |
| `bridge/setup-dell.sh` | Idempotent installer |
| `bridge/scale_ocr.py` | Ground-truth OCR (scaffolded, not yet live) |
| `scripts/check-state.sh` | One-command live audit |
| `scripts/patch-n8n-to-dell.sh` | Phase 4 cutover |
| `n8n/aperture-workflow-LIVE-snapshot.json` | Rollback artifact (if present) |
| `outreach/adam-followup-2026-04-17.md` | Outbound client ask tracking |

## 13. Tasks this spec does NOT answer

- How to run the actual Phase 2-3 Dell session commands (see DELL-SESSION.md)
- How to invoke the cutover (see ACT.md Q4 or `scripts/patch-n8n-to-dell.sh`)
- How to recover from specific n8n workflow corruptions (see learned patterns registry)

---

## Instructions for a fresh instance reading this

1. **Read this file top to bottom.** Don't skim §11 (open questions).
2. **Cross-check against primary sources.** For every claim in §3 (architecture), §5 (requirements), §7 (fragilities), §9 (deployment state), verify against the actual files, git history, or Gmail threads. Note any contradictions.
3. **Surface gaps.** What's missing from this spec that a future maintainer would need? Add them.
4. **Challenge the hypotheses.** §11 is explicitly a list of "I don't know for sure." For each item, decide: can I verify this from primary sources, or does Mika need to answer?
5. **Update this file in place.** Rewrite §§ where you're more confident than I was. Move items from §11 into their proper section once verified. Add a "Revision log" entry at the bottom with date + what you changed.
6. **Flag disagreements.** If you think I'm wrong about something non-trivial, don't silently overwrite; add a `> CHALLENGE:` block with your claim + evidence.
