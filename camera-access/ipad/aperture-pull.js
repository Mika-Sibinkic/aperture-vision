// Aperture — iPad on-device camera pull (Scriptable)
// ---------------------------------------------------------------------------
// WHY THIS EXISTS
// The mounted Hikvision at the Cul2vate dock is LAN-only (ISAPI digest, HTTP).
// The iPad is the one always-on-site device already on that LAN and already the
// button-press front end. iOS will NOT let an app be a persistent inbound
// server (apps get suspended), so we do NOT make the iPad a server. Instead we
// use the *tap moment* (foreground): when a volunteer taps, this script pulls a
// fresh JPEG straight from the camera over the LAN, then POSTs it to the Vercel
// relay -> n8n -> vision (NIM) -> Google Sheet. No Mac, no LAN box, no
// Hik-Connect cloud (which is dead for this camera).
//
// AUTH: Hikvision ISAPI uses HTTP Digest. Scriptable/Shortcuts are NOT bound by
// browser mixed-content/CORS rules, so an HTTP pull from an HTTPS-origin app is
// fine here. The digest response math below is verified against the RFC 2617
// test vector (see camera-access/ipad/README.md).
//
// SECRETS: nothing is hardcoded. On first run the script prompts for camera IP,
// user, password, snapshot path, and relay URL, and stores them in the iOS
// Keychain (Scriptable's Keychain API). To re-run setup: long-press the script
// in Scriptable and pass the argument "setup", or delete the keys.
// ---------------------------------------------------------------------------

// ---- MD5 (Paul Johnston / blueimp core, public domain; ASCII/creds path) ----
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

// ---- Digest header construction (RFC 2617, qop=auth) ----
function parseAuthHeader(h) {
  // h = 'Digest realm="...", qop="auth", nonce="...", opaque="...", algorithm=MD5'
  var out = {};
  var body = h.replace(/^Digest\s+/i, "");
  var re = /(\w+)=(?:"([^"]*)"|([^,]*))/g, m;
  while ((m = re.exec(body)) !== null) out[m[1].toLowerCase()] = (m[2] !== undefined ? m[2] : m[3]).trim();
  return out;
}

function buildDigestAuth(user, pass, method, uri, wwwAuth, cnonce, nc) {
  var p = parseAuthHeader(wwwAuth);
  var realm = p.realm || "";
  var nonce = p.nonce || "";
  var qop = p.qop ? p.qop.split(",")[0].trim() : "";
  var algorithm = (p.algorithm || "MD5").toUpperCase();

  var HA1 = md5(user + ":" + realm + ":" + pass);
  if (algorithm === "MD5-SESS") HA1 = md5(HA1 + ":" + nonce + ":" + cnonce);
  var HA2 = md5(method + ":" + uri);

  var response;
  if (qop === "auth" || qop === "auth-int") {
    response = md5([HA1, nonce, nc, cnonce, qop, HA2].join(":"));
  } else {
    response = md5(HA1 + ":" + nonce + ":" + HA2);
  }

  var parts = [
    'username="' + user + '"',
    'realm="' + realm + '"',
    'nonce="' + nonce + '"',
    'uri="' + uri + '"',
    'response="' + response + '"'
  ];
  if (p.algorithm) parts.push("algorithm=" + p.algorithm);
  if (qop) { parts.push("qop=" + qop); parts.push("nc=" + nc); parts.push('cnonce="' + cnonce + '"'); }
  if (p.opaque) parts.push('opaque="' + p.opaque + '"');
  return "Digest " + parts.join(", ");
}

// ---- Node test hook (skipped inside Scriptable) ----
if (typeof module !== "undefined" && module.exports) {
  module.exports = { md5: md5, parseAuthHeader: parseAuthHeader, buildDigestAuth: buildDigestAuth };
}

// ===========================================================================
// Scriptable runtime (only executes on-device; skipped when required by Node)
// ===========================================================================
async function main() {
  const K = {
    base: "aperture_cam_base",
    user: "aperture_cam_user",
    pass: "aperture_cam_pass",
    path: "aperture_snapshot_path",
    relay: "aperture_relay_url",
    location: "aperture_location"
  };

  const arg = (typeof args !== "undefined" && args.shortcutParameter) || "";
  const needSetup = arg === "setup" || !Keychain.contains(K.base) || !Keychain.contains(K.pass);
  if (needSetup) await runSetup(K);

  const base = Keychain.get(K.base).replace(/\/+$/, "");
  const user = Keychain.get(K.user);
  const pass = Keychain.get(K.pass);
  const path = Keychain.contains(K.path) ? Keychain.get(K.path) : "/ISAPI/Streaming/channels/101/picture";
  const relay = Keychain.get(K.relay);
  const location = Keychain.contains(K.location) ? Keychain.get(K.location) : "Cul2vate, Ellington Ag Center";
  const url = base + path;

  // 1) unauthenticated GET -> expect 401 with WWW-Authenticate: Digest
  const r1 = new Request(url);
  r1.method = "GET";
  await r1.load();
  const status1 = r1.response.statusCode;

  let imageData; // Data (JPEG bytes)
  if (status1 === 200) {
    imageData = r1.responseData;               // some firmwares allow basic/none
  } else if (status1 === 401) {
    const www = headerLookup(r1.response.headers, "www-authenticate");
    if (!www || !/^Digest/i.test(www)) throw new Error("camera did not offer Digest auth: " + String(www));
    const cnonce = uuidHex();
    const nc = "00000001";
    const authHeader = buildDigestAuth(user, pass, "GET", path, www, cnonce, nc);

    const r2 = new Request(url);
    r2.method = "GET";
    r2.headers = { Authorization: authHeader };
    imageData = await r2.load();               // JPEG bytes
    if (r2.response.statusCode !== 200) throw new Error("auth GET failed: HTTP " + r2.response.statusCode);
  } else {
    throw new Error("camera GET unexpected HTTP " + status1);
  }

  const b64 = imageData.toBase64String();

  // 2) POST the frame to the Vercel relay (relay injects the shared token to n8n)
  const post = new Request(relay);
  post.method = "POST";
  post.headers = { "Content-Type": "application/json" };
  post.body = JSON.stringify({
    description: "",
    image_b64: b64,
    triggered_at: new Date().toISOString(),
    location: location,
    source: "aperture-ipad"
  });
  const result = await post.loadJSON();

  await presentResult(result, post.response ? post.response.statusCode : 0);
  Script.complete();
}

async function runSetup(K) {
  const fields = [
    ["Camera base URL", K.base, "http://<camera-ip>", false],
    ["Camera username", K.user, "admin", false],
    ["Camera password", K.pass, "", true],
    ["Snapshot path", K.path, "/ISAPI/Streaming/channels/101/picture", false],
    ["Relay URL", K.relay, "https://<vercel-app-host>/api/donate", false],
    ["Location label", K.location, "Cul2vate, Ellington Ag Center", false]
  ];
  for (const [label, key, placeholder, secure] of fields) {
    const a = new Alert();
    a.title = "Aperture setup";
    a.message = label;
    const existing = Keychain.contains(key) ? Keychain.get(key) : placeholder;
    if (secure) a.addSecureTextField(label, ""); else a.addTextField(label, existing);
    a.addAction("Save");
    await a.present();
    const v = a.textFieldValue(0);
    if (v && v.length) Keychain.set(key, v);
    else if (!secure && !Keychain.contains(key)) Keychain.set(key, placeholder);
  }
}

function headerLookup(headers, name) {
  const want = name.toLowerCase();
  for (const k in headers) if (k.toLowerCase() === want) return headers[k];
  return null;
}

function uuidHex() {
  return UUID.string().replace(/-/g, "").toLowerCase().slice(0, 16);
}

async function presentResult(result, httpStatus) {
  const t = new UITable();
  t.showSeparators = true;
  const head = t.addRow();
  head.isHeader = true;
  const ok = result && (result.weight_lbs !== undefined && result.weight_lbs !== null);
  head.addText(ok ? (Number(result.weight_lbs).toFixed(1) + " lbs") : (result && result.error ? "Failed" : "Logged"));
  const add = (k, v) => { const r = t.addRow(); r.addText(String(k)); r.addText(v === undefined || v === null ? "—" : String(v)); };
  if (result) {
    add("Item", result.item_type);
    if (result.confidence !== undefined && result.confidence !== null) add("Confidence", Math.round(result.confidence * 100) + "%");
    add("ChArUco", result.charuco_detected ? "calibrated" : "fallback");
    if (result.farmbrite_id) add("Farmbrite", "#" + result.farmbrite_id);
    if (result.error) add("Error", result.error);
    if (result.raw) add("Raw", result.raw);
  }
  add("HTTP", httpStatus);
  await t.present();
}

if (typeof Keychain !== "undefined") { main().catch((e) => { logError(e); const a = new Alert(); a.title = "Aperture error"; a.message = String(e && e.message ? e.message : e); a.addAction("OK"); a.present(); }); }
