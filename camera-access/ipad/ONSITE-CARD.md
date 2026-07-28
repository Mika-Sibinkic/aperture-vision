# Aperture — on-site card (iPad setup)

**Time: ~10 minutes. Nothing to type. Nothing to configure.**

Everything server-side is already live and tested end-to-end (Vercel, n8n, NVIDIA
NIM vision, Google Sheet). The only thing that has never run on this iPad is the
camera pull, and step 3 proves it in one tap before any volunteer sees it.

---

## Before you leave the house

1. On the Mac, run:
   ```bash
   python3 scripts/make-ipad-script.py
   ```
   That writes **`camera-access/ipad/Aperture.local.js`** — already filled in with
   the camera address, login, and relay URL.
2. **AirDrop that file to the iPad now**, while you're on a network you trust.
   (It contains the camera password. AirDrop only. Not email, not Slack.)

If you forget this step you can still do it on site — AirDrop works device-to-device.

---

## On site — 4 steps

### 1. Put the iPad on the Cul2vate Wi-Fi
The same network as the camera. This is the only network requirement.

### 2. Install Scriptable and import the file
- App Store → **Scriptable** (free) → install.
- Open the AirDropped `Aperture.local.js` → **Open in Scriptable** → it appears
  in the script list. Long-press it → **Rename** → `Aperture`.

### 3. Run the self-test — this is the gate
In Scriptable, long-press **Aperture** → **Run with Parameter** → type `selftest` → Run.

You'll get a checklist:

```
✅ Camera reachable + password accepted     412 KB
✅ Photo prepared for upload                268 KB
✅ Weight came back + row logged            0.0 lbs empty
✅ ALL GOOD — ready for volunteers
```

- **All ✅ → you're done. Go to step 4.**
- **Any ❌ → stop and do the one thing next to it** (see the short list below).
  Don't debug anything else; every other hop is already proven.

The self-test writes one row to the Sheet labelled `SELF-TEST — ignore this row`.
Delete it later if you care; it's harmless.

### 4. Make it the "app" for volunteers
- Scriptable → long-press **Aperture** → **Add to Home Screen** → name it
  **Aperture**, pick the icon → Add.
- Settings → **Display & Brightness → Auto-Lock → Never**.
- Keep the iPad **on the charger**.
- Optional lockdown: Settings → Accessibility → **Guided Access** → on. Then open
  Aperture and triple-click the side button so volunteers can't leave the app.

Do one real tap with an actual donation in the taped zone. You should see a
weight in about 12 seconds.

---

## What to tell the volunteers

> Put the donation inside the yellow tape. Tap **Aperture**. Wait for the weight.
> That's it — it's already recorded.

---

## If the self-test shows a ❌ — one action each

| What it says | Do exactly this |
|---|---|
| ❌ Camera — *can't reach the camera* | The iPad is on the wrong Wi-Fi. Switch it to the Cul2vate network and run the self-test again. |
| ❌ Camera — *rejected the saved password* | The camera password changed. Text Mika; he regenerates the file in 1 minute. |
| ❌ Server — anything | The internet at the site is down, or the vision service is briefly out. Wait 60 seconds, run the self-test again. If it fails twice, text Mika — nothing on the iPad is wrong. |

That's the whole list. There is no other failure mode to chase: the camera hop is
the only piece that isn't already verified from off-site.

---

## Facts worth knowing (not needed for setup)

- A tap takes **~12 seconds** end to end.
- The iPad is **not** a server. It only pulls the frame while you're looking at it,
  which is why nothing has to stay running when the iPad sleeps.
- Every tap writes a row to the **Donations** sheet. Weight, item, confidence, and
  the model version are all logged, so accuracy work later is just reading history.
- If the iPad is off or asleep, nothing breaks — the next tap works normally.
