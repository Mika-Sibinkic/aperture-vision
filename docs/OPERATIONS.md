# Aperture — operations & developer capability

> State: live · Optionality: low · Open to Change: yes — this file is the single
> authoritative answer to "what is running right now, and what can I change without
> driving to the site?". Update it in the same session as any architecture change.

Last verified: **2026-08-02**.

---

## 1. What is actually running

| Layer | What | Where | Verified |
|---|---|---|---|
| Capture | Hikvision AcuSense <device-serial>, ISAPI digest over LAN at `<camera-ip>` | Cul2vate dock | frames pulled 2026-06-15 |
| Trigger | Scriptable script on the on-site iPad, foreground at tap time | iPad | digest math verified vs RFC 2617; on-device hop pending |
| Relay | Next.js route `/api/donate` (archives photo, forwards, writes record) | Vercel, `<vercel-app-host>` | live |
| Orchestration | n8n workflow `<n8n-workflow-id>`, **17 nodes**, active | n8n Cloud, project **Main** | live |
| Vision | `nvidia/nemotron-nano-12b-v2-vl` via NVIDIA NIM, prompt **v0.6-net** | NIM (hosted) | 9.8–12.5 s per tap |
| Log | Google Sheet `Donations` | Google | live |
| Photo + record store | Vercel Blob, **private** store `<blob-store>` | Vercel | live |
| Export | `/api/export` → CSV (`?format=json`, `?since=YYYY-MM-DD`) | Vercel | live |
| Inventory | Farmbrite Draft order, `product_id` + `qty` in pounds | Farmbrite | verified + cleaned up |

**No self-managed server anywhere.** Nothing to restart, no tunnel, no VM. The only
on-premise compute is the iPad, and only while a volunteer is looking at it.

---

## 2. What the developer can change remotely (no site visit)

Everything below is reachable from any machine with this repo and the credentials in
`SECRETS.local.md`.

| Want to change | How | Risk |
|---|---|---|
| Vision model, prompt, weight logic, Farmbrite mapping, Sheet columns | edit `prompts/weight-estimation.md` or `scripts/rewire-n8n-ipad-nim.py`, then run the script | backs up + verifies + reads back; `--restore` rolls back |
| Relay behaviour, CSV export, timeouts | edit `app/`, `vercel --prod` | previous deployment is one click away in the Vercel dashboard |
| Swap the vision provider | create an n8n credential, point the vision node at it | one credential change |
| Farmbrite product map | re-run the fetch in `scripts/farmbrite-setup.py` | read-only unless `--create` |
| **The iPad script itself** | see §3 — iCloud Drive | file edit, no visit |
| Check health from anywhere | `python3 scripts/vision-regression-test.py --e2e` | read-only probe |
| Read what happened | `/api/export`, the Google Sheet, n8n execution log | read-only |

### Requires being on site (short list)

- Anything physical: camera aim/power, the ChArUco board, the tape, the injector.
- The **router** (DHCP reservation, Wi-Fi).
- **First** install of the iPad script, and the iPad's power/Wi-Fi/Guided Access.

That is the entire list. There is no remote-desktop dependency anywhere.

---

## 3. Updating the iPad without visiting

iOS does not permit remote-control hosting, so there is no RustDesk equivalent for the
iPad. The supported path is **iCloud Drive**:

1. On the iPad, after installing Scriptable, confirm iCloud is enabled for it
   (Settings → Apple ID → iCloud → Scriptable → on).
2. A folder then appears on the Mac at
   `~/Library/Mobile Documents/iCloud~dk~simonbs~Scriptable/Documents`.
3. Editing `Aperture.js` there syncs to the iPad automatically.

So iPad-side fixes ship as a file edit. Regenerate with
`python3 scripts/make-ipad-script.py` and copy the result into that folder.

**Caveat:** the generated build contains the camera password. It is gitignored and must
move by AirDrop or iCloud only — never email or chat.

---

## 4. On confidence — why it is not shown to anyone

The vision model emits a `confidence` number. **It is uncalibrated and currently
carries almost no information.**

- It is a self-reported token, not a measured probability. Nothing checks whether
  things it scores 0.9 actually land within 10%.
- It comes from the same pass that produced the weight, so its errors are correlated:
  a confidently wrong estimate arrives with confident confidence.
- **Measured:** across the first 10 real records it took exactly **two** values —
  0.85 and 0.95 (spread 0.1). It does not discriminate between good and bad readings.

It is therefore removed from every human-facing surface (iPad screen, CSV, Google
Sheet, Farmbrite notes). It is retained **only** in the raw per-donation record, where
it costs nothing and can be checked later.

**It becomes meaningful only after ground truth exists.** With real weighed items we
can test whether confidence correlates with actual error. If it does, it earns a job
(route low-confidence loads to a manual weigh). If it does not, delete it.

---

## 5. Accuracy — the honest position

The weights are **not validated against a scale on this camera**. Structural work has
been done to make them as good as possible without ground truth:

- Container counting instead of pile-volume guessing.
- Tare removed (it double-subtracted).
- `temperature: 0` and a deterministic weight path — same image gives the same number
  (measured 60/60/60 lb across three runs).
- A plausibility guard flags anything over 2000 lb from a 6×6 ft zone.

None of that establishes error tolerance. Until real weights flow through
`/api/correct`, treat the numbers as **operational record and trend**, not audited
poundage. `docs/AUDIT-PREHANDOFF.md` §B4 tracks this.

---

## 6. Scheduled decay — things that will break on their own

| Item | Symptom when it lapses | Fix |
|---|---|---|
| NVIDIA NIM free credits | every tap fails (401/429) | swap the n8n vision credential to another provider |
| Camera DHCP lease (unless reserved) | every tap fails, "can't reach the camera" | reserve the IP on the Eero |
| Google Sheets OAuth in n8n | Sheet rows stop; photo + record still safe | re-authorise the n8n credential |
| Farmbrite token (a personal user token) | Farmbrite entries stop; taps unaffected | move to a dedicated integration user |
| Vercel Blob free tier (~1 GB ≈ 4,000 photos) | archiving stops, `archive_error` set; taps unaffected | prune old photos or upgrade |
| n8n Cloud monthly execution cap | **all taps fail** | verify the plan's ceiling against volume |

Nothing currently alerts on any of these — that is the largest sustainability gap and
is tracked as `docs/AUDIT-PREHANDOFF.md` §B2.

---

## 7. Farmbrite API facts worth not rediscovering

- Auth: `Authorization: Bearer <token>`. The token lives at
  **Users → <user> → Settings → Allow API Access**.
- `qty` and `price` on an order item **must be strings**. Numbers return
  `500 "Invalid Order Item"`.
- An order with **no items is accepted silently** — an unmatched product must never
  fall through to an empty order.
- **`GET /orders` excludes drafts.** A just-created draft was absent from all 5 pages
  while being retrievable by id. Use **`?status=Draft`** to list them. This is why the
  Farmbrite write is chained ahead of the response: the order id cannot be looked up
  afterwards, so it must be carried forward.
- List responses can be served from cache (`"cached": true`), so a deleted order may
  still appear in a listing. Confirm deletion with a direct `GET /orders/<id>` (404).

## 8. Command reference

```bash
# health, from anywhere
python3 scripts/vision-regression-test.py --e2e

# change the model / prompt / mapping, then apply (backs up, verifies, reads back)
python3 scripts/rewire-n8n-ipad-nim.py --dry-run
python3 scripts/rewire-n8n-ipad-nim.py
python3 scripts/rewire-n8n-ipad-nim.py --restore n8n/backups/<file>.json

# rebuild the iPad file (contains the camera password; AirDrop/iCloud only)
python3 scripts/make-ipad-script.py

# inspect / refresh Farmbrite
export FARMBRITE_API_KEY='...'      # SECRETS.local.md
python3 scripts/farmbrite-setup.py

# ship relay changes
npm run build && vercel --prod --yes

# the running log
curl https://<vercel-app-host>/api/export -o donations.csv
```
