# Aperture — on-site card (iPad setup)

**Time: ~10 minutes. Nothing to type. Nothing to configure.**

Everything on the server side is already live and tested end to end. The only thing that has never run on this iPad is the
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
In the **Scriptable app**, just tap **Aperture**. A menu appears — choose **System check**.

(The menu only appears inside the Scriptable app. The Home Screen icon you add in step 4
goes straight to logging a donation, so volunteers never see it.)

You'll get a checklist:

```
✅ Camera connected                         412 KB
✅ Photo ready                              268 KB
✅ Weight recorded                          0.0 lbs empty
✅ ALL GOOD — ready for volunteers
```

- **All ✅ → you're done. Go to step 4.**
- **Any ❌ → stop and do the one thing next to it** (see the short list below).
  Don't debug anything else; every other hop is already proven.

The self-test writes one row labelled `SYSTEM CHECK — ignore this row`.
Delete it later if you care; it's harmless.

### 4. Make it the "app" for volunteers — THIS is the handoff
Until this is done there is no front end; the script only exists inside Scriptable.

**Use the Shortcuts app — not Scriptable's own "Add to Home Screen".**
Scriptable's button opens a `data:text/html;base64,...` page that is supposed to
redirect to `scriptable:///run/Aperture`. In a normal Safari tab WebKit refuses that
navigation and shows *"Not allowed to use restricted network port"*. The Shortcuts
route avoids the whole mechanism. [Observed on the iPad 2026-08-02]

1. Open the **Shortcuts** app.
2. **+** → search **Scriptable** → add **Run Script**.
3. **Script** → **Aperture**.
4. Under **Texts**, tap **Add new item** and type: `log`
   REQUIRED. Without a parameter the script shows the operator menu instead of the
   app. `log` opens the Aperture front end. [VERIFIED 2026-08-02]
5. Turn **Run in App** ON — required, because the script presents alerts and tables.
6. Leave **Show When Run** ON.
7. Name it **Aperture**, pick an icon.
8. Share icon → **Add to Home Screen** → **Add**.
- The Home Screen icon runs the donation flow **directly** — one tap, no menu. That is
  what volunteers use. The menu (System check / Recent log) only ever appears when the
  script is opened inside the Scriptable app, which is the operator path.
- While you are in Script Settings, turn **Always Run in App** ON. The script presents
  alerts and tables; this avoids a memory failure when launched from the Home Screen.
- Settings → **Display & Brightness → Auto-Lock → Never**.
- Keep the iPad **on the charger**.
- Optional lockdown: Settings → Accessibility → **Guided Access** → on. Then open
  Aperture and triple-click the side button so volunteers can't leave the app.

Do one real tap with an actual donation in the taped zone. You should see a
weight in about 12 seconds.

---

## What to tell the volunteers

> Put the donation inside the yellow tape. Tap **Aperture**. Type what it is.
> Press the green button and wait for the weight. That's it — it's recorded.
> If you log something by mistake, press **Undo** next to it in the Recent list.

The app is a real screen, not a system popup: APERTURE header, an item box, one big
green button, the weight in large type, and a **Recent** list with an **Undo** button
on each entry. Volunteers never need the Scriptable app.

---

## If the self-test shows a ❌ — one action each

| What it says | Do exactly this |
|---|---|
| ❌ Camera — *can't reach the camera* | The iPad is on the wrong Wi-Fi. Switch it to the Cul2vate network and run the self-test again. |
| ❌ Camera — *rejected the saved password* | The camera password changed. Text Mika; he regenerates the file in 1 minute. |
| ❌ Server — anything | The site internet is down, or the service is briefly out. Wait 60 seconds and run the self-test again. If it fails twice, text Mika — nothing on the iPad is wrong. |

That's the whole list. There is no other failure mode to chase: the camera hop is
the only piece that isn't already verified from off-site.

---

## Facts worth knowing (not needed for setup)

- A tap takes **~12 seconds** end to end.
- The iPad is **not** a server. It only pulls the frame while you're looking at it,
  which is why nothing has to stay running when the iPad sleeps.
- Every tap writes a row to the **Donations** sheet, so the full intake history is
  always available to export.
- If the iPad is off or asleep, nothing breaks — the next tap works normally.
