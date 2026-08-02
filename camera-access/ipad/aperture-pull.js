// Aperture — iPad on-tap camera pull (Scriptable)
// ---------------------------------------------------------------------------
// The volunteer taps this. It pulls a fresh frame from the MOUNTED Hikvision
// over the Cul2vate LAN, posts it to the Vercel relay, and shows the weight.
//
// WHY THE IPAD: the camera is LAN-only (ISAPI digest over HTTP) and Hik-Connect
// cloud-pull is dead for this model. The iPad is the one always-on-site device
// on that LAN and is already the button. iOS suspends background apps, so the
// iPad is NOT a server — it pulls at the moment of the tap, while foreground.
// A Scriptable request is not bound by browser mixed-content/CORS rules, which
// is exactly why the PWA could not do this and this can.
//
// CONFIG: `scripts/make-ipad-script.py` emits a pre-configured copy of this
// file (gitignored) with CONFIG filled in, so nothing is typed on site. If
// CONFIG is left blank, the script falls back to the iOS Keychain and prompts
// once. This committed copy never contains credentials.
//
// HOW MODES ARE CHOSEN (no typing, no parameters):
//   Home-screen icon  -> logs a donation immediately. One tap. This is the volunteer
//                        path and must never show a menu.
//   Opened inside the -> shows a short menu: Log a donation / System check /
//   Scriptable app       Recent log (undo) / Re-enter settings.
//
// `config.runsInApp` is what distinguishes the two, so the operator gets the tools and
// the volunteer gets one button. A parameter is still honoured if one is supplied by a
// Shortcut or the scriptable:///run URL scheme.
// ---------------------------------------------------------------------------

const CONFIG = {
  base: "",        // e.g. "http://<camera-ip>"   (filled by make-ipad-script.py)
  user: "",        // e.g. "admin"
  pass: "",
  path: "/ISAPI/Streaming/channels/101/picture",
  relay: "https://<vercel-app-host>/api/donate",
  exportUrl: "https://<vercel-app-host>/api/export",
  voidUrl: "https://<vercel-app-host>/api/void",
  location: "Cul2vate, Ellington Ag Center",
  maxPixels: 1600, // longest edge sent upstream; keeps the tap fast on site WiFi
};

// ---- MD5 (Paul Johnston / blueimp core, public domain) ---------------------
function md5(str) {
  function safeAdd(x, y){var lsw=(x&0xffff)+(y&0xffff);var msw=(x>>16)+(y>>16)+(lsw>>16);return (msw<<16)|(lsw&0xffff);}
  function rol(num,cnt){return (num<<cnt)|(num>>>(32-cnt));}
  function cmn(q,a,b,x,s,t){return safeAdd(rol(safeAdd(safeAdd(a,q),safeAdd(x,t)),s),b);}
  function ff(a,b,c,d,x,s,t){return cmn((b&c)|(~b&d),a,b,x,s,t);}
  function gg(a,b,c,d,x,s,t){return cmn((b&d)|(c&~d),a,b,x,s,t);}
  function hh(a,b,c,d,x,s,t){return cmn(b^c^d,a,b,x,s,t);}
  function ii(a,b,c,d,x,s,t){return cmn(c^(b|~d),a,b,x,s,t);}
  function binlMD5(x,len){
    x[len>>5]|=0x80<<(len%32);
    x[(((len+64)>>>9)<<4)+14]=len;
    var i,olda,oldb,oldc,oldd,a=1732584193,b=-271733879,c=-1732584194,d=271733878;
    for(i=0;i<x.length;i+=16){
      olda=a;oldb=b;oldc=c;oldd=d;
      a=ff(a,b,c,d,x[i],7,-680876936);d=ff(d,a,b,c,x[i+1],12,-389564586);c=ff(c,d,a,b,x[i+2],17,606105819);b=ff(b,c,d,a,x[i+3],22,-1044525330);
      a=ff(a,b,c,d,x[i+4],7,-176418897);d=ff(d,a,b,c,x[i+5],12,1200080426);c=ff(c,d,a,b,x[i+6],17,-1473231341);b=ff(b,c,d,a,x[i+7],22,-45705983);
      a=ff(a,b,c,d,x[i+8],7,1770035416);d=ff(d,a,b,c,x[i+9],12,-1958414417);c=ff(c,d,a,b,x[i+10],17,-42063);b=ff(b,c,d,a,x[i+11],22,-1990404162);
      a=ff(a,b,c,d,x[i+12],7,1804603682);d=ff(d,a,b,c,x[i+13],12,-40341101);c=ff(c,d,a,b,x[i+14],17,-1502002290);b=ff(b,c,d,a,x[i+15],22,1236535329);
      a=gg(a,b,c,d,x[i+1],5,-165796510);d=gg(d,a,b,c,x[i+6],9,-1069501632);c=gg(c,d,a,b,x[i+11],14,643717713);b=gg(b,c,d,a,x[i],20,-373897302);
      a=gg(a,b,c,d,x[i+5],5,-701558691);d=gg(d,a,b,c,x[i+10],9,38016083);c=gg(c,d,a,b,x[i+15],14,-660478335);b=gg(b,c,d,a,x[i+4],20,-405537848);
      a=gg(a,b,c,d,x[i+9],5,568446438);d=gg(d,a,b,c,x[i+14],9,-1019803690);c=gg(c,d,a,b,x[i+3],14,-187363961);b=gg(b,c,d,a,x[i+8],20,1163531501);
      a=gg(a,b,c,d,x[i+13],5,-1444681467);d=gg(d,a,b,c,x[i+2],9,-51403784);c=gg(c,d,a,b,x[i+7],14,1735328473);b=gg(b,c,d,a,x[i+12],20,-1926607734);
      a=hh(a,b,c,d,x[i+5],4,-378558);d=hh(d,a,b,c,x[i+8],11,-2022574463);c=hh(c,d,a,b,x[i+11],16,1839030562);b=hh(b,c,d,a,x[i+14],23,-35309556);
      a=hh(a,b,c,d,x[i+1],4,-1530992060);d=hh(d,a,b,c,x[i+4],11,1272893353);c=hh(c,d,a,b,x[i+7],16,-155497632);b=hh(b,c,d,a,x[i+10],23,-1094730640);
      a=hh(a,b,c,d,x[i+13],4,681279174);d=hh(d,a,b,c,x[i],11,-358537222);c=hh(c,d,a,b,x[i+3],16,-722521979);b=hh(b,c,d,a,x[i+6],23,76029189);
      a=hh(a,b,c,d,x[i+9],4,-640364487);d=hh(d,a,b,c,x[i+12],11,-421815835);c=hh(c,d,a,b,x[i+15],16,530742520);b=hh(b,c,d,a,x[i+2],23,-995338651);
      a=ii(a,b,c,d,x[i],6,-198630844);d=ii(d,a,b,c,x[i+7],10,1126891415);c=ii(c,d,a,b,x[i+14],15,-1416354905);b=ii(b,c,d,a,x[i+5],21,-57434055);
      a=ii(a,b,c,d,x[i+12],6,1700485571);d=ii(d,a,b,c,x[i+3],10,-1894986606);c=ii(c,d,a,b,x[i+10],15,-1051523);b=ii(b,c,d,a,x[i+1],21,-2054922799);
      a=ii(a,b,c,d,x[i+8],6,1873313359);d=ii(d,a,b,c,x[i+15],10,-30611744);c=ii(c,d,a,b,x[i+6],15,-1560198380);b=ii(b,c,d,a,x[i+13],21,1309151649);
      a=ii(a,b,c,d,x[i+4],6,-145523070);d=ii(d,a,b,c,x[i+11],10,-1120210379);c=ii(c,d,a,b,x[i+2],15,718787259);b=ii(b,c,d,a,x[i+9],21,-343485551);
      a=safeAdd(a,olda);b=safeAdd(b,oldb);c=safeAdd(c,oldc);d=safeAdd(d,oldd);
    }
    return [a,b,c,d];
  }
  function binl2hex(bin){var h="0123456789abcdef",s="";for(var i=0;i<bin.length*4;i++){s+=h.charAt((bin[i>>2]>>((i%4)*8+4))&0xf)+h.charAt((bin[i>>2]>>((i%4)*8))&0xf);}return s;}
  function str2binl(str){var bin=[];var mask=(1<<8)-1;for(var i=0;i<str.length*8;i+=8){bin[i>>5]|=(str.charCodeAt(i/8)&mask)<<(i%32);}return bin;}
  return binl2hex(binlMD5(str2binl(str),str.length*8));
}

// ---- HTTP Digest (RFC 2617) ------------------------------------------------
function parseAuthHeader(h) {
  var out = {}, body = String(h).replace(/^Digest\s+/i, "");
  var re = /(\w+)=(?:"([^"]*)"|([^,]*))/g, m;
  while ((m = re.exec(body)) !== null) out[m[1].toLowerCase()] = (m[2] !== undefined ? m[2] : m[3]).trim();
  return out;
}

function buildDigestAuth(user, pass, method, uri, wwwAuth, cnonce, nc) {
  var p = parseAuthHeader(wwwAuth);
  var realm = p.realm || "", nonce = p.nonce || "";
  var qop = p.qop ? p.qop.split(",")[0].trim() : "";
  var algorithm = (p.algorithm || "MD5").toUpperCase();
  var HA1 = md5(user + ":" + realm + ":" + pass);
  if (algorithm === "MD5-SESS") HA1 = md5(HA1 + ":" + nonce + ":" + cnonce);
  var HA2 = md5(method + ":" + uri);
  var response = (qop === "auth" || qop === "auth-int")
    ? md5([HA1, nonce, nc, cnonce, qop, HA2].join(":"))
    : md5(HA1 + ":" + nonce + ":" + HA2);
  var parts = ['username="'+user+'"', 'realm="'+realm+'"', 'nonce="'+nonce+'"',
               'uri="'+uri+'"', 'response="'+response+'"'];
  if (p.algorithm) parts.push("algorithm=" + p.algorithm);
  if (qop) { parts.push("qop=" + qop); parts.push("nc=" + nc); parts.push('cnonce="'+cnonce+'"'); }
  if (p.opaque) parts.push('opaque="' + p.opaque + '"');
  return "Digest " + parts.join(", ");
}

// Node test hook (skipped on-device)
if (typeof module !== "undefined" && module.exports) {
  module.exports = { md5: md5, parseAuthHeader: parseAuthHeader, buildDigestAuth: buildDigestAuth };
}

// ===========================================================================
// Scriptable runtime
// ===========================================================================
const KEYS = {
  base: "aperture_cam_base", user: "aperture_cam_user", pass: "aperture_cam_pass",
  path: "aperture_snapshot_path", relay: "aperture_relay_url", location: "aperture_location",
};

function headerLookup(headers, name) {
  const want = name.toLowerCase();
  for (const k in headers) if (k.toLowerCase() === want) return headers[k];
  return null;
}

// ---------------------------------------------------------------------------
// Crash-safe local state.
//
// A loading dock is a hostile place for a tap-and-wait UI: the volunteer waits
// 10-25 s, assumes it didn't work, and taps again — which without this would log
// the SAME donation twice and silently inflate the day's poundage. That is the
// worst failure this system can have, because nothing looks broken.
//
// State lives in a plain file, so it survives the app being killed, the iPad
// being powered off mid-run, and iOS suspending the script.
// ---------------------------------------------------------------------------
const IN_FLIGHT_WINDOW_MS = 75_000;   // > worst observed round trip (~27 s) with margin

// Resolved lazily, never at load time: nothing about starting this script should
// be able to throw before the error handler in main() is installed.
function statePath() {
  const fm = FileManager.local();
  return fm.joinPath(fm.libraryDirectory(), "aperture-state.json");
}

function readState() {
  try {
    const fm = FileManager.local();
    const p = statePath();
    if (!fm.fileExists(p)) return {};
    return JSON.parse(fm.readString(p)) || {};
  } catch (e) {
    return {};                                   // corrupt state must never block a tap
  }
}

function writeState(patch) {
  try {
    const next = Object.assign(readState(), patch);
    FileManager.local().writeString(statePath(), JSON.stringify(next));
    return next;
  } catch (e) {
    return {};                                   // storage failure must never block a tap
  }
}

// Retry once on a transient blip (Wi-Fi hiccup, camera busy, upstream 5xx).
// Anything still failing after this is a real condition worth showing a human.
async function withRetry(label, fn) {
  try {
    return await fn();
  } catch (first) {
    await new Promise((r) => Timer.schedule(1200, false, r));
    try {
      return await fn();
    } catch (second) {
      throw new Error(String(second && second.message ? second.message : second));
    }
  }
}

async function resolveConfig(mode) {
  if (CONFIG.base && CONFIG.pass) return CONFIG;            // pre-configured build
  if (mode === "setup") await runSetup();
  for (const k of ["base", "user", "pass", "relay"]) {
    if (!Keychain.contains(KEYS[k])) { await runSetup(); break; }
  }
  return {
    base: Keychain.get(KEYS.base), user: Keychain.get(KEYS.user), pass: Keychain.get(KEYS.pass),
    path: Keychain.contains(KEYS.path) ? Keychain.get(KEYS.path) : CONFIG.path,
    relay: Keychain.get(KEYS.relay),
    location: Keychain.contains(KEYS.location) ? Keychain.get(KEYS.location) : CONFIG.location,
    maxPixels: CONFIG.maxPixels,
    exportUrl: CONFIG.exportUrl,
    voidUrl: CONFIG.voidUrl,
  };
}

async function runSetup() {
  const fields = [
    ["Camera address", KEYS.base, "http://<camera-ip>", false],
    ["Camera username", KEYS.user, "admin", false],
    ["Camera password", KEYS.pass, "", true],
    ["Snapshot path", KEYS.path, CONFIG.path, false],
    ["Relay URL", KEYS.relay, CONFIG.relay, false],
    ["Location label", KEYS.location, CONFIG.location, false],
  ];
  for (const [label, key, fallback, secure] of fields) {
    const a = new Alert();
    a.title = "Aperture setup";
    a.message = label;
    const existing = Keychain.contains(key) ? Keychain.get(key) : fallback;
    if (secure) a.addSecureTextField(label, ""); else a.addTextField(label, existing);
    a.addAction("Save");
    await a.present();
    const v = a.textFieldValue(0);
    if (v && v.length) Keychain.set(key, v);
    else if (!secure) Keychain.set(key, fallback);
  }
}

// Pull one JPEG from the mounted camera over the LAN.
async function grabFrame(cfg) {
  const url = cfg.base.replace(/\/+$/, "") + cfg.path;

  const probe = new Request(url);
  probe.method = "GET";
  probe.timeoutInterval = 20;
  let probeData;
  try {
    probeData = await probe.load();
  } catch (e) {
    throw new Error(
      "Can't reach the camera at " + cfg.base + ".\n\n" +
      "Check the iPad is on the Cul2vate Wi-Fi, then tap again."
    );
  }

  const status = probe.response.statusCode;
  if (status === 200) return probeData;                     // no auth required
  if (status !== 401) throw new Error("Camera replied HTTP " + status + " instead of a photo.");

  const www = headerLookup(probe.response.headers, "www-authenticate");
  if (!www || !/^Digest/i.test(String(www))) {
    throw new Error("Camera did not offer Digest login (got: " + String(www) + ").");
  }

  const authed = new Request(url);
  authed.method = "GET";
  authed.timeoutInterval = 25;
  authed.headers = {
    Authorization: buildDigestAuth(cfg.user, cfg.pass, "GET", cfg.path, www,
                                   UUID.string().replace(/-/g, "").toLowerCase().slice(0, 16), "00000001"),
  };
  const data = await authed.load();
  const code = authed.response.statusCode;
  if (code === 401) throw new Error("Camera rejected the saved password. Re-run setup with the correct admin password.");
  if (code !== 200) throw new Error("Camera replied HTTP " + code + " on the authenticated request.");
  return data;
}

// Shrink the 5MP frame so the upload is quick on site Wi-Fi.
function shrink(data, maxPixels) {
  try {
    const img = Image.fromData(data);
    if (!img) return data;
    const longest = Math.max(img.size.width, img.size.height);
    if (!longest || longest <= maxPixels) return data;
    const scale = maxPixels / longest;
    const ctx = new DrawContext();
    ctx.size = new Size(Math.round(img.size.width * scale), Math.round(img.size.height * scale));
    ctx.respectScreenScale = false;
    ctx.drawImageInRect(img, new Rect(0, 0, ctx.size.width, ctx.size.height));
    return Data.fromJPEG(ctx.getImage());
  } catch (e) {
    return data;                                            // never block a tap on resizing
  }
}

async function postToRelay(cfg, b64, description, donationId) {
  const post = new Request(cfg.relay);
  post.method = "POST";
  post.timeoutInterval = 120;
  post.headers = { "Content-Type": "application/json" };
  post.body = JSON.stringify({
    description: description || "",
    image_b64: b64,
    triggered_at: new Date().toISOString(),
    location: cfg.location,
    // Stable across an automatic retry, so if the first attempt actually landed
    // server-side and only the reply was lost, the duplicate is identifiable by
    // donation_id instead of masquerading as a second real donation.
    donation_id: donationId || undefined,
    source: "aperture-ipad",
  });
  const text = await post.loadString();
  let parsed;
  try { parsed = JSON.parse(text); }
  catch (e) { throw new Error("Server sent an unreadable reply: " + String(text).slice(0, 200)); }
  if (parsed && parsed.error) throw new Error(String(parsed.error));
  return parsed;
}

async function showResult(result) {
  const t = new UITable();
  t.showSeparators = true;
  const head = t.addRow();
  head.isHeader = true;
  head.height = 70;
  const hasWeight = result && typeof result.weight_lbs === "number";
  head.addText(hasWeight ? result.weight_lbs.toFixed(1) + " lbs" : "Logged");
  const add = (k, v) => { const r = t.addRow(); r.addText(String(k)); r.addText(v == null ? "—" : String(v)); };
  // Client-facing screen: the weight IS the record. No model scores, no internal
  // diagnostics — those stay in the operator's export, not in front of volunteers.
  add("Item", result.item_type);
  add("Recorded", new Date().toLocaleTimeString());
  await t.present();
}

async function showError(message) {
  const a = new Alert();
  a.title = "Couldn't log this donation";
  a.message = String(message);
  a.addAction("OK");
  await a.present();
}

// One tap that proves every hop, in plain language.
async function selfTest(cfg) {
  const steps = [];
  const t = new UITable();
  const render = () => {
    t.removeAllRows();
    const h = t.addRow(); h.isHeader = true; h.addText("Aperture self-test");
    for (const s of steps) { const r = t.addRow(); r.addText(s.ok ? "✅ " + s.name : "❌ " + s.name); r.addText(s.detail || ""); }
    t.reload();
  };
  await t.present(false);

  let frame = null;
  try {
    frame = await grabFrame(cfg);
    steps.push({ ok: true, name: "Camera connected", detail: Math.round(frame.toBase64String().length / 1024) + " KB" });
  } catch (e) {
    steps.push({ ok: false, name: "Camera", detail: String(e.message).split("\n")[0] });
    render();
    return steps;
  }
  render();

  const small = shrink(frame, cfg.maxPixels);
  steps.push({ ok: true, name: "Photo ready", detail: Math.round(small.toBase64String().length / 1024) + " KB" });
  render();

  try {
    const res = await postToRelay(cfg, small.toBase64String(), "SYSTEM CHECK — ignore this row");
    const ok = res && (typeof res.weight_lbs === "number" || res.item_type);
    steps.push({ ok: ok, name: "Weight recorded",
                 detail: ok ? ((typeof res.weight_lbs === "number" ? res.weight_lbs.toFixed(1) + " lbs" : "") + " " + (res.item_type || "")).trim() : "no weight" });
  } catch (e) {
    steps.push({ ok: false, name: "Server", detail: String(e.message).slice(0, 90) });
  }
  render();

  const allOk = steps.every((s) => s.ok);
  steps.push({ ok: allOk, name: allOk ? "ALL GOOD — ready for volunteers" : "NOT READY — see the ❌ above", detail: "" });
  render();
  return steps;
}

// Live progress, shown immediately. The volunteer must SEE that something is
// happening, or they will tap again during the wait.
function progressTable() {
  const t = new UITable();
  t.showSeparators = true;
  const render = (lines, headline) => {
    t.removeAllRows();
    const h = t.addRow();
    h.isHeader = true;
    h.height = 60;
    h.addText(headline);
    for (const line of lines) {
      const r = t.addRow();
      r.addText(line);
    }
    t.reload();
  };
  return { table: t, render };
}

async function runDonation(cfg) {
  const state = readState();
  const now = Date.now();

  // Guard: a run is already in flight -> do NOT start a second one.
  if (state.inFlightAt && now - state.inFlightAt < IN_FLIGHT_WINDOW_MS) {
    const a = new Alert();
    a.title = "Already logging";
    const last = state.lastResult;
    a.message =
      "This donation is still being weighed — please wait a few seconds.\n\n" +
      "Do NOT tap again; tapping twice records the same donation twice." +
      (last ? `\n\nLast logged: ${last.summary} at ${last.at}` : "");
    a.addAction("OK");
    await a.present();
    return;
  }

  // Claim the slot before any network work, so a mid-run power-off still
  // leaves a marker rather than a half-logged donation with no trace.
  const donationId = UUID.string().toLowerCase();
  writeState({ inFlightAt: now, inFlightId: donationId });

  const ui = progressTable();
  ui.render(["Reading the camera…"], "Weighing");
  ui.table.present(false);

  try {
    const frame = await withRetry("camera", () => grabFrame(cfg));
    ui.render(["Photo captured", "Weighing…", "", "This takes about 10–25 seconds."], "Weighing");

    const small = shrink(frame, cfg.maxPixels);
    const result = await withRetry("relay", () => postToRelay(cfg, small.toBase64String(), "", donationId));

    const summary = typeof result.weight_lbs === "number"
      ? `${result.weight_lbs.toFixed(1)} lbs ${result.item_type || ""}`.trim()
      : "logged";
    writeState({
      inFlightAt: null,
      inFlightId: null,
      lastResult: { summary, at: new Date().toLocaleTimeString(), donation_id: donationId },
    });
    await showResult(result);
  } catch (e) {
    // Release the lock so the next tap can retry immediately — a failed run must
    // not lock the dock out for the full window.
    writeState({ inFlightAt: null, inFlightId: null });
    throw e;
  }
}

// Recent log with one-tap undo. Mis-taps happen on a dock — wrong item typed, photo
// taken before the load was staged, a duplicate. Without this the only fix is asking
// someone to hand-edit a spreadsheet later, which never happens.
async function showHistory(cfg) {
  const req = new Request((cfg.exportUrl || CONFIG.exportUrl) + "?format=json");
  req.timeoutInterval = 60;
  let rows = [];
  try {
    const data = await req.loadJSON();
    rows = Array.isArray(data.rows) ? data.rows : [];
  } catch (e) {
    await showError("Couldn't load the recent log: " + (e.message || e));
    return;
  }
  rows.reverse();                                   // newest first
  const recent = rows.slice(0, 25);

  const t = new UITable();
  t.showSeparators = true;
  const draw = () => {
    t.removeAllRows();
    const h = t.addRow();
    h.isHeader = true;
    h.height = 60;
    h.addText("Recent donations", recent.length ? "Tap one to undo it" : "Nothing logged yet");
    for (const r of recent) {
      const row = new UITableRow();
      row.height = 58;
      const when = String(r.triggered_at || "").replace("T", " ").slice(5, 16);
      const lbs = typeof r.weight_lbs === "number" ? r.weight_lbs.toFixed(1) + " lbs" : "—";
      row.addText(`${lbs}  ${r.item_type || ""}`.trim(), `${when}   ${r.description || ""}`.trim());
      row.onSelect = async () => {
        const a = new Alert();
        a.title = "Undo this donation?";
        a.message = `${lbs} ${r.item_type || ""}\n${when}\n\nIt will be removed from the record and from Farmbrite. The photo is kept.`;
        a.addDestructiveAction("Undo it");
        a.addCancelAction("Keep it");
        if ((await a.present()) !== 0) return;

        const v = new Request(cfg.voidUrl || CONFIG.voidUrl);
        v.method = "POST";
        v.timeoutInterval = 60;
        v.headers = { "Content-Type": "application/json" };
        v.body = JSON.stringify({ donation_id: r.donation_id, reason: "undone on the iPad" });
        try {
          const res = await v.loadJSON();
          const done = new Alert();
          done.title = res && res.ok ? "Removed" : "Couldn't remove it";
          done.message = res && res.ok
            ? "That donation is no longer in the record."
            : String((res && res.error) || "Unknown problem.");
          done.addAction("OK");
          await done.present();
          if (res && res.ok) {
            const i = recent.indexOf(r);
            if (i >= 0) recent.splice(i, 1);
            draw();
          }
        } catch (e) {
          await showError("Couldn't remove it: " + (e.message || e));
        }
      };
      t.addRow(row);
    }
    t.reload();
  };
  draw();
  await t.present();
}

// Operator menu — only ever shown when opened from inside the Scriptable app.
async function chooseMode() {
  const a = new Alert();
  a.title = "Aperture";
  a.message = "What would you like to do?";
  a.addAction("Log a donation");        // 0
  a.addAction("System check");          // 1
  a.addAction("Recent log (undo)");     // 2
  a.addAction("Re-enter settings");     // 3
  a.addCancelAction("Close");           // -1
  const picked = await a.present();
  return ["", "selftest", "history", "setup"][picked] ?? null;
}

async function main() {
  let mode = ((typeof args !== "undefined" && (args.shortcutParameter || (args.plainTexts && args.plainTexts[0]))) || "")
    .toString().trim().toLowerCase();

  // No parameter and opened inside the app -> operator menu. From the home-screen
  // icon (runsInApp === false) fall straight through to logging.
  if (!mode && typeof config !== "undefined" && config.runsInApp) {
    mode = await chooseMode();
    if (mode === null) { Script.complete(); return; }
  }

  const cfg = await resolveConfig(mode);

  if (mode === "selftest") { await selfTest(cfg); Script.complete(); return; }
  if (mode === "history" || mode === "undo") { await showHistory(cfg); Script.complete(); return; }
  if (mode === "reset") {                      // clears a stuck lock; never needed normally
    writeState({ inFlightAt: null, inFlightId: null });
    const a = new Alert(); a.title = "Aperture reset"; a.message = "Ready for the next donation."; a.addAction("OK");
    await a.present(); Script.complete(); return;
  }

  await runDonation(cfg);
  Script.complete();
}

if (typeof Keychain !== "undefined") {
  main().catch(async (e) => {
    logError(e);
    await showError(e && e.message ? e.message : e);
    Script.complete();
  });
}
