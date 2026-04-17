# Deployment Playbook — Tomorrow's Site Visit

Goal: drive up, install hardware, leave with Aperture live on the iPad and
logging test donations to Farmbrite.

---

## Phase 0 — Night before (at your Mac, no Cul2vate access)

Plan for 30–60 minutes. Everything here is blocked by no external dependencies
except your own accounts.

- [ ] `cd aperture && ./scripts/setup.sh` — installs deps, generates icons,
      mints `APERTURE_SHARED_TOKEN`, links Vercel, deploys a first pass.
      Save the token it prints.
- [ ] Provision n8n:
  - [ ] Decide: **n8n Cloud** (new workspace for Aperture, or reuse existing) vs
        **self-host** at Cul2vate (Option D in `camera-access/README.md`).
        Default recommendation: n8n Cloud, new workflow under your existing
        Microscout-adjacent account.
  - [ ] Import `n8n/aperture-workflow.json`. Leave inactive.
  - [ ] Generate `APERTURE_SHARED_TOKEN`: `openssl rand -hex 32`. Paste into
        n8n Variables AND save for Vercel step.
- [ ] Provision Vercel project:
  - [ ] `npx vercel link` (new project "aperture")
  - [ ] `npx vercel env add N8N_WEBHOOK_URL production` (leave blank — fill
        after n8n URL exists below)
  - [ ] `npx vercel env add APERTURE_SHARED_TOKEN production` (paste token)
  - [ ] `npx vercel env add NEXT_PUBLIC_LOCATION_LABEL production` →
        "Cul2vate — Ellington Ag Center"
- [ ] Provision credentials in n8n:
  - [ ] OpenAI API key → OpenAI credential
  - [ ] (Camera digest auth — fill in DURING install once you see the
        first-boot password)
  - [ ] (Farmbrite header auth — fill in DURING install once the client contact pulls the
        API key)
- [ ] Camera-access decision:
  - [ ] If Option A (Cloudflare Tunnel on a bring-your-own device), run:
        ```
        ./scripts/deploy-tunnel.sh aperture-cul2vate camera.example.com TBD
        ```
        (use `TBD` for the camera IP; the script writes a config you edit
        on-site once you see the real IP.) DNS propagates while you drive.
- [ ] Paste the contents of `prompts/weight-estimation.md` (from `## System
      prompt` onward) into the n8n Vision node's System Message.
- [ ] Do a local dev smoke test:
  - [ ] `npm run dev`
  - [ ] Hit button. Confirm /api/donate returns 502 with n8n timeout (expected
        — no camera yet). That proves the front→back→n8n wiring works.
- [ ] Deploy Vercel:
  - [ ] `npx vercel --prod`
  - [ ] Save the URL. Send yourself an iMessage with it so you can paste it on
        the iPad Safari without typing.

---

## Phase 1 — On arrival at Cul2vate (30 minutes)

- [ ] **Sign install (Joshua already there if the client contact isn't)**
  - [ ] Hold the 36×44" Dibond flush against the brick. Level. Mark the 6
        pre-drilled hole centers through the board with pencil.
  - [ ] Hammer-drill each with the Tapcon bit.
  - [ ] Set 6× ¼" Tapcons with 1–2 spacers behind the board per hole for
        airflow + flatness.
  - [ ] Verify the board is square + not bowed. ChArUco will fail if warped.
- [ ] **Camera mount**
  - [ ] Mount bracket above the loading bay entry, aimed so the 6×6 taped
        zone (next step) AND the ChArUco sign are both in frame.
  - [ ] 20–40 ft standoff distance per PRD.
  - [ ] Attach Hikvision <device-serial>. Snug but don't over-torque.
- [ ] **Floor taping**
  - [ ] Tape a 6×6 ft zone on the floor centered under the camera's view.
  - [ ] Use the yellow tape the client contact ordered. High-contrast against concrete.
- [ ] **Cabling**
  - [ ] Run Cat6 from WiFi extender side → PoE injector → camera.
  - [ ] Plug PoE injector into the outlet the client contact identified (Mar 30 thread).
  - [ ] Camera should power on — green LED visible.

## Phase 2 — Network bring-up (20 minutes)

- [ ] Laptop on Cul2vate WiFi. Run `arp -a` or use Fing app on phone to find
      the camera's LAN IP.
- [ ] Browser → `http://<camera-ip>` → first-boot wizard:
  - [ ] Set admin password (store in 1Password — label "Cul2vate Hikvision").
  - [ ] Set static IP (recommended) or reserve DHCP on the router.
  - [ ] Set NTP.
  - [ ] Enable ISAPI (usually on by default).
- [ ] Camera web UI → adjust varifocal zoom/focus so the 6×6 zone + ChArUco
      sign are both cleanly in frame. Lock focus.
- [ ] Confirm snapshot URL returns a JPEG:
  ```bash
  curl -u admin:PASS --digest \
    "http://<camera-ip>/ISAPI/Streaming/channels/101/picture" \
    -o test.jpg && open test.jpg
  ```
- [ ] **Camera-access bridge** — pick one from `camera-access/README.md`:
  - [ ] Option A: plug in your pre-flashed Cloudflare-Tunnel device.
        Edit `cloudflared-config.yml` with the real camera IP. Restart
        cloudflared. `curl https://camera.example.com/…` from your
        phone (off WiFi) should return the same JPEG.
  - [ ] Whatever option you picked, end state: a public HTTPS URL that
        returns a fresh snapshot on demand.
- [ ] Paste that URL into n8n → Variables → `HIKVISION_CAMERA_URL`.
- [ ] Paste camera admin u/p into n8n → Credentials → Hikvision Camera.

## Phase 3 — Farmbrite wiring (15 minutes — the client contact needed)

- [ ] the client contact logs into Farmbrite → Settings → API → generate API key.
- [ ] Auto-discover the right endpoint:
      ```
      FARMBRITE_API_KEY=<key> ./scripts/discover-farmbrite-endpoint.sh
      ```
      Script probes 7 endpoints × 3 auth header formats and reports which
      combination returns 2xx. Copy those three values.
- [ ] Paste the three values into n8n Variables + Credentials:
      - `FARMBRITE_API_BASE`
      - `FARMBRITE_INVENTORY_ENDPOINT`
      - Auth header + value (→ HTTP Header Auth credential in n8n)

## Phase 4 — n8n activation & end-to-end (10 minutes)

- [ ] Activate the workflow.
- [ ] Copy the Production Webhook URL.
- [ ] `npx vercel env add N8N_WEBHOOK_URL production` → paste. Redeploy:
      `npx vercel --prod`.
- [ ] On iPad Safari: open the Vercel URL, Add to Home Screen, name "Aperture".
- [ ] Take 3 test photos:
  1. Empty zone → expect `inside_zone: false`, no Farmbrite write.
  2. Single box of cans in the zone → should return a weight, Farmbrite
     entry visible in the Farmbrite UI.
  3. Mixed-produce pallet → weight should be in range (compare to the client contact's
     rough mental estimate; no scale needed yet).
- [ ] Snap a screenshot of each result in the PWA. Put in `docs/pilot-day1/`
      for the residual log baseline.

## Phase 5 — Hand-off to the client contact/Joshua (10 minutes)

- [ ] **Kiosk-mode the iPad** per `docs/IPAD-SETUP.md` (§1–§4) — Guided
      Access locked to Aperture, auto-lock never, Do Not Disturb on, iPad
      plugged in permanently. Save the Guided Access passcode to 1Password.
- [ ] Write this on a sticky note on the iPad: "Place donation in yellow
      box → tap green button → wait ~8 sec → weight appears and logs to
      Farmbrite."
- [ ] Confirm the iPad stays plugged in to a power source.
- [ ] Show the client contact where to find the Farmbrite entries (name/tag filter).
- [ ] Ask the client contact to text you the first real-donation weight + his paper-scale
      comparison so you can log the first residual.

## Phase 6 — Drive home, commit everything (25 minutes)

- [ ] Snapshot the camera's final mount angle + the iPad on the wall into
      `docs/pilot-day1/photos/`.
- [ ] Git commit the real IP + domain into `camera-access/cloudflared-config.yml`
      (ONLY if not secret) and push.
- [ ] Update `memory/project_aperture.md` with the actual camera IP, Farmbrite
      endpoint, n8n workflow ID, Vercel URL.
- [ ] Schedule a 2-day check-in text to the client contact.

---

## If anything goes sideways

- **Camera not reachable from your laptop**: check PoE injector LEDs; reseat
  Cat6. Often it's a loose termination.
- **Vision model returns non-JSON**: look at the prompt — did you forget to
  set "Response Format: JSON object" in the OpenAI node?
- **Farmbrite returns 401**: the API key header format is probably wrong.
  Test with curl first. If they use `X-Api-Key` instead of `Authorization`,
  change the n8n credential type.
- **Tunnel URL returns 502**: cloudflared can't reach the camera. Check the
  camera IP in the config. Firewall rules on the Cul2vate router?
- **Everything works but weight is way off**: that's expected for v0.1. It'll
  improve as the Phase 2 RL loop feeds residuals back. Log every real weight
  comparison so we have data.

Don't escalate to the client contact for a fix you can verify yourself
(per `verify-before-escalate` rule). Reproduce the failure first.
