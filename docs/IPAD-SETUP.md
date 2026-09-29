# iPad kiosk setup: Cul2vate

The AI model runs in n8n Cloud + OpenAI. The iPad is a kiosk: button +
description box + result display. So "always on" means "always available
for a volunteer to tap," not "always running a model."

This doc is the exact settings sequence to run once, on-site, during the
install. Budget ~15 minutes (plus any iOS update time; see §0).

---

## §0: iOS update (if needed)

Per the client contact's Mar 31 text, the iPad has been off for a while. Before anything
else:

1. Plug into power and the WiFi extender's network.
2. Settings → General → Software Update → install whatever's pending.
3. Wait. Don't start anything else during the update.

If it's stuck on an ancient iOS (< 11.3), PWAs won't install to home screen.
Realistically any iPad from the last 6 years is fine.

---

## §1: Power + placement

- Plug into the extension cord the client contact ran. Confirm the battery icon shows a
  lightning bolt.
- Mount the iPad on the wall near the staging zone (tape, Command strips,
  or whatever bracket the client contact has).
- Height: waist-to-chest level of a standing volunteer.
- Lightning cable should be zip-tied so it doesn't tug.

---

## §2: System settings (do these in order)

1. Connect WiFi: Settings → Wi-Fi → Cul2vate's network → Auto-Join ON.
2. **Disable Auto-Lock**
   Settings → Display & Brightness → Auto-Lock → **Never**.
3. **Disable Raise to Wake** (prevents accidental screen-on when jostled)
   Settings → Display & Brightness → Raise to Wake → **Off**.
4. **Disable Notifications on Lock Screen** (keeps the button UI unobscured)
   Settings → Notifications → Show Previews → **Never**.
5. Do Not Disturb: enable the Focus mode so incoming calls/FaceTime
   don't interrupt a donation log.
   Settings → Focus → Do Not Disturb → turn on. Set schedule "Always".
6. **Battery: Low Power Mode: Off** (prevents throttling).
7. Brightness: Settings → Display & Brightness → around 70%. Auto-
   Brightness ON for outdoor light variance.

---

## §3: Install the Aperture PWA

1. Open Safari.
2. Paste the Vercel URL (from your iMessage to yourself during Phase 0).
3. Verify it loads: dark background, "APERTURE" header, green "Log
   Donation" button, description textarea.
4. Tap the **Share** icon (box with up-arrow, top right).
5. Scroll down in the share sheet → **Add to Home Screen**.
6. Name: "Aperture". Tap **Add**.
7. Close Safari.
8. Launch Aperture from the home screen; it should open **without** the
   Safari chrome (full-screen PWA, thanks to `display: standalone` in the
   manifest).

---

## §4: Lock to the Aperture app (Guided Access)

This prevents volunteers from accidentally switching apps, opening Settings,
or getting stuck on a notification.

1. Settings → Accessibility → **Guided Access** → turn **On**.
2. Tap "Passcode Settings" → Set Guided Access Passcode. Use something
   you'll remember but volunteers can't guess. **Save it to 1Password under
   "Cul2vate Aperture iPad".**
3. Optional but recommended: turn on "Accessibility Shortcut" so triple-
   click of the Side button toggles Guided Access.

### To enter Guided Access for the first time:

1. Launch Aperture from the home screen.
2. Triple-click the Side button (or Home button on older iPads).
3. Tap **Start** top-right.
4. Set a timer? Leave **off** (we want unlimited duration).
5. Optionally tap "Options" at bottom-left and disable **Sleep/Wake Button**
   to prevent accidental screen off.

The iPad is now locked to Aperture until you exit Guided Access (triple-
click → enter passcode → End).

### To hand the iPad off to the client contact/Joshua:

Don't exit Guided Access when you leave. Tell the client contact the triple-click +
passcode only if he needs it for iOS updates; day-to-day he never exits.

---

## §5: Verify

Press the green button with no donation in the zone. Expected:
- Button goes grey, shows "Analyzing…"
- 5-10 sec later: result card shows "Outside the yellow zone, reposition
  and retry." (because the vision model returned `inside_zone: false`)

Press it again with a test box inside the zone. Expected:
- Result card shows a weight in lbs + item type + confidence + Farmbrite
  record ID.

If both work, kiosk setup is done.

---

## §6: If the iPad dies / crashes / is unplugged

- Donations can't be logged during the outage.
- Once power is restored: press Home button (or wake), unlock (if passcode
  is set; recommend NO passcode on Cul2vate's end since Guided Access
  provides lockdown), tap the Aperture icon.
- Guided Access will re-engage automatically if "Accessibility Shortcut"
  was configured, otherwise triple-click to re-enter.

If the client contact reports the kiosk isn't responding:
1. Ask him to force-quit: swipe up from bottom to reveal app switcher, swipe
   Aperture up and away. Re-open from home screen.
2. If still broken: hold Side + Volume Up to restart the iPad. Guided
   Access auto-resumes on boot.

---

## §7: What NOT to configure

- **Don't** enable Screen Time; it conflicts with Guided Access scheduling.
- **Don't** sign in to Apple ID; the iPad is a kiosk, not a personal
  device. An Apple ID pulls email/Messages/Photos notifications in.
- **Don't** install AnyDesk/TeamViewer for remote support; if Aperture
  breaks, Mika drives over. That's the whole deal.
- **Don't** set a lock-screen passcode. Guided Access already prevents app
  switching; a passcode on top of that just annoys the client contact when he reboots.
