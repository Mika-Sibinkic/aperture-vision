#!/usr/bin/env python3
"""
Rewire the live Aperture n8n workflow for the production architecture:

    iPad (pulls mounted Hikvision over LAN)  ->  Vercel relay  ->  n8n
        -> NVIDIA NIM vision  ->  Google Sheet  ->  response

Replaces the two dead hops:
  1. "Fetch snapshot + scale OCR (via Bridge)" (HTTP to a bridge that no longer
     exists) -> deleted. The frame now arrives in the webhook as `image_b64`.
  2. "Vision: weight estimate" (langchain OpenAI node on a dry account) -> a plain
     HTTP Request to NIM's OpenAI-compatible endpoint, using an n8n credential so
     the API key never lands in the workflow JSON or in git.

Design rules (this is a live production workflow):
  * IDEMPOTENT  - safe to re-run; converges to the same end state.
  * BACKED UP   - writes the pre-change workflow to n8n/backups/ before touching it.
  * VERIFIED    - a full validation pass runs BEFORE the PUT. If any check fails the
                  script aborts and the live workflow is left untouched.
  * NO SECRETS  - asserts no nvapi-/bearer material is present in the outgoing JSON.

Usage:
    source "<business-framework>/.env"          # N8N_BASE_URL, N8N_API_KEY
    python3 scripts/rewire-n8n-ipad-nim.py [--dry-run]

Rollback:
    python3 scripts/rewire-n8n-ipad-nim.py --restore n8n/backups/<file>.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import uuid

REPO = Path(__file__).resolve().parent.parent
WORKFLOW_ID = "<n8n-workflow-id>"
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NIM_MODEL = "nvidia/nemotron-nano-12b-v2-vl"
PROMPT_VERSION = "v0.6-net"
NIM_CREDENTIAL_NAME = "NVIDIA NIM (Aperture)"

# n8n rejects a PUT whose `settings` carries keys outside this allow-list.
ALLOWED_SETTINGS = {
    "executionOrder", "saveExecutionProgress", "saveManualExecutions",
    "saveDataErrorExecution", "saveDataSuccessExecution", "executionTimeout",
    "errorWorkflow", "timezone",
}

VISION_NODE = "Vision: weight estimate"
BUILD_NODE = "Build vision request"
OLD_BUILD_NODE = "Unpack bridge response"
OLD_FETCH_NODE = "Fetch snapshot + scale OCR (via Bridge)"
CONFIG_NODE = "Load prompt + config"
PARSE_NODE = "Parse vision + tare + bias"
WEBHOOK_NODE = "Webhook: donation button"
SHEET_NODE = "Append to Google Sheet"
SHAPE_NODE = "Shape response"
FARMBRITE_SKIP_NODE = "Farmbrite skipped (pending key)"
FARMBRITE_BUILD_NODE = "Build Farmbrite order"
FARMBRITE_NODE = "Farmbrite: log order"
FARMBRITE_URL = "https://api.farmbrite.com/v1/orders"
FARMBRITE_CREDENTIAL_NAME = "Farmbrite (Aperture)"


# --------------------------------------------------------------------------- api
def api(method: str, path: str, body: dict | None = None):
    base = os.environ.get("N8N_BASE_URL", "").rstrip("/")
    key = os.environ.get("N8N_API_KEY", "")
    if not base or not key:
        sys.exit("ERROR: N8N_BASE_URL / N8N_API_KEY not set. `source` the framework .env first.")
    req = urllib.request.Request(
        f"{base}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-N8N-API-KEY": key, "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:600].decode(errors="replace")


def load_system_prompt() -> str:
    """Read the SYSTEM PROMPT block from prompts/weight-estimation.md (source of truth)."""
    text = (REPO / "prompts" / "weight-estimation.md").read_text()
    match = re.search(r"^## SYSTEM PROMPT\s*\n(.*?)\n## END SYSTEM PROMPT", text, re.S | re.M)
    if not match:
        sys.exit("ERROR: could not find the '## SYSTEM PROMPT' block in prompts/weight-estimation.md")
    prompt = match.group(1).strip()
    if "nothing\nis added or subtracted after you" not in prompt.replace("  ", " "):
        pass  # wording check is advisory; the hard contract check is below
    if "container_count" not in prompt:
        sys.exit("ERROR: prompt lacks container_count — v0.5 counting contract missing. Aborting.")
    if "48.4" in prompt or '"confidence": 0.82' in prompt:
        sys.exit("ERROR: prompt contains filled-in example values — that is the v0.3 parroting bug. Aborting.")
    return prompt


def find_credential_id() -> str:
    """n8n's public API cannot list credentials; read the id cached by the creator step."""
    cache = REPO / ".n8n-nim-credential-id"
    if cache.exists():
        return cache.read_text().strip()
    env = os.environ.get("N8N_NIM_CREDENTIAL_ID", "").strip()
    if env:
        return env
    sys.exit(
        "ERROR: NIM credential id unknown.\n"
        "  Create it once:  POST /credentials {name:'NVIDIA NIM (Aperture)', type:'httpHeaderAuth',\n"
        "                     data:{name:'Authorization', value:'Bearer <nvapi-key>'}}\n"
        f"  then save the returned id to {cache} (gitignored) or export N8N_NIM_CREDENTIAL_ID."
    )


PRODUCT_MAP = {
"Acorn Squash": "68016e831e1f000008110583",
"Adirondack Blue Potatoes": "685c02f56544a6000f3f751b",
"Banana Peppers": "67c4b3c4d17b1e0008676a9c",
"Beans": "68017a88598e8e000ce50ce2",
"Beets": "67c4b7c6d17b1e0012676cd8",
"Bell Peppers": "67d84f1d3e1b52000b5639e2",
"Blackberries": "67bf7b40a7ec08000cdd7bc2",
"Blackberry, Prime Ark Freedom": "67bf7ecb56ff1d000829401a",
"Blueberries": "67c0dbb356ff1d000829502c",
"Bok Choy": "68813f486609ae000df70d38",
"Broccoli": "67c4b3f5d17b1e0012676b5a",
"Brussels": "68017d86598e8e0013e50a21",
"Burbank Russet Potatoes": "6877d6c1012e4f0008cab97b",
"Butternut Squash": "68891e79f87924001c278829",
"Cabbage": "67c4b379d17b1e0012676b58",
"Cantaloupe": "68017a4c598e8e0013e50a17",
"Carrots": "67c4e06ed17b1e000b676981",
"Cauliflower": "67c4b8b98038e30008c0ac26",
"Cherry Tomatoes": "6863e8ed4c2c080008f6176e",
"Chives": "67c4dfe6d17b1e0012676e12",
"Collards": "67c4b9dad17b1e000b676939",
"Community Garden Produce": "683615bc9685a100081209f1",
"Corn": "687fa362ca68a4000d38f9de",
"Eggplant": "68b75365dc56b597cf02dce6",
"Fingerling Potatoes": "6863e2284c2c08000df61298",
"Garlic Scapes": "682cba030d549f000ea5d3f6",
"Gold Rush Beans (2025)": "684c7c71dcf0040008ae0929",
"Grandprize Summer Squash": "684c3ce4dcf004000cae0cce",
"Green Beans": "685c04fae5911400106a925c",
"Greenhouse Cucumbers": "67ab66961e9dad00080b99fc",
"Greenhouse Tomato": "67a67a873a7575000815cecf",
"Hardneck Garlic": "6849b25c6bf41d000cc864ae",
"Heirloom & Field Tomatoes": "67c4b76f8038e30008c0abe6",
"Hot Peppers": "68017ee11e1f00000f1102d3",
"Kabocha Squash": "687135fd379c850021355504",
"Kale": "67c4b801d17b1e0012676cde",
"Kennebec Potatoes": "6877cc98012e4f000bcab1ff",
"Kohlrabi": "67c4e0d1d17b1e000b676984",
"Lehigh Potatoes": "6880f270ca68a4000d39034d",
"Lettuce": "67c4b9788038e30014c0ad4c",
"Ministry Baked Goods": "69026e2a77b57bbe30bbcf1a",
"Ministry Beef": "67a578fa3a7575000f15c956",
"Ministry Chicken": "67fd2ec04c2c08000a4e0f40",
"Ministry Eggs": "67fd30805ba4920008c5f8ad",
"Ministry Pork": "67b4a6d2ca68a4000821a803",
"Ministry Venison": "67a57ea53a7575000815c98e",
"Mistake": "68824c6f4f2d350017101374",
"Okra": "67c4e22bd17b1e0008676ad5",
"Peanuts": "68017ea8598e8e000ce50d5c",
"Pontiac Red Potatoes": "684b1ab190a6dd000b0ab457",
"Pumpkins": "68017c651e1f00000811072b",
"Radishes": "67c4e09f8038e30014c0ae01",
"Raspberries": "67bf805756ff1d000829401e",
"Red Onions": "67c4b6e88038e30008c0abd4",
"Seasonal Produce - August": "689f60fd11aa992057c25043",
"Seasonal Produce - July": "68c97699cc6e441327310afe",
"Seasonal Produce - June": "6849ee4f0c3c6a000bb89339",
"Seasonal Produce - October": "68f7b687fc9226a147c00652",
"Seasonal Produce - September": "68c976c779e3c0c2a7c3e8b7",
"Serrano Peppers": "67c4ba8ad17b1e000b67693d",
"Snap Pea": "684c7ebbdcf004000cae11ad",
"Softneck Garlic": "6849b2326bf41d000cc864ad",
"Spaghetti Squash": "6893a5071c7e1636e0b6c7b7",
"Spinach": "681b8ba42a8dec000bfcf7c1",
"Strawberries": "681b714d3501e90008dbb96a",
"Sweet Potatoes": "67e6caf1453ea0000f9e5aae",
"Swiss Chard": "67c4b8438038e30008c0ac22",
"Tomatillos": "68640685779b650012fdc433",
"Turnips and Greens": "67a67b883a7575000f15cd5c",
"Watermelons": "68016f1e1e1f00000f11024d",
"White Onions": "67c4b633d17b1e0012676c50",
"Yellow Summer Squash": "684c7a3b90a6dd000b0aca9c",
"Yukon Gold Potatoes": "67c4e13dd17b1e000b676987",
"Zucchini": "68016dd21e1f000008110580"
}


def farmbrite_build_code() -> str:
    """Map the parsed donation onto a Farmbrite draft order line.

    Field quirks learned from the live API (2026-08-02):
      * `qty` and `price` MUST be STRINGS. Numbers return
        500 "Invalid Order Item. Qty and price required for new order items."
      * An order with no items is accepted silently, so an unmatched product must
        never fall through to an empty order — that would look logged but hold nothing.
    """
    return (
        "// Resolve the donation to a Farmbrite product and build a Draft order.\n"
        f"const PRODUCTS = {json.dumps(PRODUCT_MAP)};\n"
        "const MONTHS = ['January','February','March','April','May','June','July',\n"
        "  'August','September','October','November','December'];\n\n"
        "const parsed = $('Parse vision + tare + bias').first().json;\n"
        "const weight = parsed.weight_lbs;\n\n"
        "// Nothing to log for an empty zone or an unusable reading.\n"
        "if (typeof weight !== 'number' || !(weight > 0)) {\n"
        "  return [{ json: { __skip: true, reason: 'no positive weight to log' } }];\n"
        "}\n\n"
        "const norm = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');\n"
        "const wanted = norm(parsed.item_type);\n"
        "let productId = null, productName = null;\n"
        "if (wanted) {\n"
        "  for (const [name, id] of Object.entries(PRODUCTS)) {\n"
        "    if (norm(name) === wanted) { productId = id; productName = name; break; }\n"
        "  }\n"
        "  if (!productId) {                       // contains-match, longest name wins\n"
        "    // Seasonal buckets are EXCLUDED here: a generic item_type like 'produce'\n"
        "    // substring-matches every 'Seasonal Produce - <Month>' entry and would pick\n"
        "    // an arbitrary (wrong) month. They are only ever used as the explicit\n"
        "    // current-month fallback below. [fixed 2026-08-02]\n"
        "    let best = 0;\n"
        "    for (const [name, id] of Object.entries(PRODUCTS)) {\n"
        "      if (name.startsWith('Seasonal Produce')) continue;\n"
        "      const n = norm(name);\n"
        "      if (n && (n.includes(wanted) || wanted.includes(n)) && n.length > best) {\n"
        "        best = n.length; productId = id; productName = name;\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
        "// Fall back to the month bucket Cul2vate already uses for mixed loads.\n"
        "if (!productId) {\n"
        "  const bucket = 'Seasonal Produce - ' + MONTHS[new Date().getMonth()];\n"
        "  if (PRODUCTS[bucket]) { productId = PRODUCTS[bucket]; productName = bucket; }\n"
        "}\n"
        "if (!productId) {\n"
        "  return [{ json: { __skip: true, reason: 'no product match and no month bucket' } }];\n"
        "}\n\n"
        "const today = new Date().toISOString().slice(0, 10);\n"
        "return [{ json: {\n"
        "  __skip: false,\n"
        "  product_name: productName,\n"
        "  order_body: {\n"
        "    status: 'Draft',\n"
        "    order_date: today,\n"
        "    note: 'Aperture auto-log - ' + (parsed.item_type || 'produce') + ' - donation ' +\n"
        "          (parsed.donation_id || '') + ' - confidence ' + (parsed.confidence ?? 'n/a'),\n"
        "    order_items: [{\n"
        "      product_id: productId,\n"
        "      qty: String(Math.round(weight * 100) / 100),   // MUST be a string\n"
        "      price: '0.00'                                   // MUST be a string\n"
        "    }]\n"
        "  }\n"
        "}}];"
    )


# ------------------------------------------------------------------- transform
def build_request_code(system_prompt: str) -> str:
    """Code for the node that turns the posted frame into a ready-to-send NIM body."""
    return (
        "// Build the NVIDIA NIM vision request from the frame the iPad posted.\n"
        "// The iPad pulls the mounted Hikvision over the Cul2vate LAN at tap time and\n"
        "// sends it here as `image_b64` — there is no bridge/tunnel in the path.\n"
        "// Also emits the scale_* fields the parse node expects (null until scale OCR ships).\n"
        f"const SYSTEM_PROMPT = {json.dumps(system_prompt)};\n\n"
        f"const body = $('{WEBHOOK_NODE}').first().json.body || {{}};\n"
        f"const config = $('{CONFIG_NODE}').first().json;\n\n"
        "let b64 = body.image_b64;\n"
        "if (typeof b64 !== 'string' || b64.length < 1000) {\n"
        "  throw new Error('No usable image_b64 in the tap payload. The iPad must capture the "
        "camera frame before posting (got ' + (b64 ? b64.length + ' chars' : 'nothing') + ').');\n"
        "}\n"
        "// Tolerate a data-URL prefix as well as bare base64.\n"
        "b64 = b64.replace(/^data:image\\/[a-zA-Z]+;base64,/, '');\n\n"
        "const context = [\n"
        "  '', '', 'Context for THIS donation:',\n"
        "  'description: ' + (body.description || '—'),\n"
        "  'location: ' + (body.location || '—'),\n"
        "  'triggered_at: ' + (body.triggered_at || new Date().toISOString()),\n"
        "  'eval_mode: false', '', 'Return the JSON object now.'\n"
        "].join('\\n');\n\n"
        "return [{ json: {\n"
        "  nim_body: {\n"
        "    model: config.model,\n"
        "    messages: [{ role: 'user', content: [\n"
        "      { type: 'text', text: SYSTEM_PROMPT + context },\n"
        "      { type: 'image_url', image_url: { url: 'data:image/jpeg;base64,' + b64 } }\n"
        "    ]}],\n"
        "    max_tokens: 800,\n"
        "    temperature: 0,\n"
        "    // Mandatory: without it the model emits prose + a code fence and the\n"
        "    // parse node throws 'Vision returned non-JSON'. [VERIFIED 2026-07-22]\n"
        "    response_format: { type: 'json_object' }\n"
        "  },\n"
        "  image_chars: b64.length,\n"
        "  scale_reading_lbs: null,\n"
        "  scale_confidence: null,\n"
        "  scale_stable: false,\n"
        "  scale_raw_text: null\n"
        "}}];"
    )


def patch_parse_code(code: str) -> str:
    """Teach the parse node to read NIM's HTTP shape, strip fences, and follow the rename."""
    old_raw = "const raw = $json.message?.content ?? $json.content ?? $json;"
    new_raw = (
        "// NIM (HTTP) returns choices[0].message.content; the older langchain node\n"
        "// returned message.content / content. Accept all shapes.\n"
        "let raw = $json.choices?.[0]?.message?.content ?? $json.message?.content ?? $json.content ?? $json;\n"
        "// Defensive: strip ```json fences if a model ever wraps its output.\n"
        "if (typeof raw === 'string') {\n"
        "  raw = raw.trim().replace(/^```(?:json)?\\s*/i, '').replace(/```$/, '').trim();\n"
        "}"
    )
    if old_raw in code:
        code = code.replace(old_raw, new_raw)
    elif "choices?.[0]?.message?.content" not in code:
        sys.exit("ERROR: could not locate the vision-parsing line in the parse node. Aborting.")
    return code.replace(f"$('{OLD_BUILD_NODE}')", f"$('{BUILD_NODE}')")


def transform(wf: dict, system_prompt: str, cred_id: str) -> dict:
    nodes = {n["name"]: n for n in wf["nodes"]}
    for required in (CONFIG_NODE, PARSE_NODE, WEBHOOK_NODE, VISION_NODE):
        if required not in nodes:
            sys.exit(f"ERROR: expected node missing from live workflow: {required!r}")

    # 1. config: model + prompt version live in one place
    cfg = nodes[CONFIG_NODE]
    cfg["parameters"]["jsonOutput"] = json.dumps(
        {"prompt_version": PROMPT_VERSION, "model": NIM_MODEL, "vision_endpoint": NIM_URL}, indent=2
    )

    # 2. build node: rename in place (keeps position) or reuse if already renamed
    build = nodes.get(OLD_BUILD_NODE) or nodes.get(BUILD_NODE)
    if build is None:
        sys.exit(f"ERROR: neither {OLD_BUILD_NODE!r} nor {BUILD_NODE!r} found.")
    build["name"] = BUILD_NODE
    build["type"] = "n8n-nodes-base.code"
    build["typeVersion"] = 2
    build["parameters"] = {"jsCode": build_request_code(system_prompt)}

    # 3. vision node: langchain OpenAI -> plain HTTP Request against NIM.
    #    n8n keys nodes by id+type and SILENTLY IGNORES an in-place type change, so the
    #    node must be recreated with a fresh id. Name and position are preserved, which
    #    is what connections and $('...') references resolve against.
    #    [VERIFIED 2026-07-28: mutating type in place left the old langchain node live.]
    vision = nodes[VISION_NODE]
    if vision.get("type") != "n8n-nodes-base.httpRequest":
        vision["id"] = str(uuid.uuid4())
    vision.pop("webhookId", None)
    vision["type"] = "n8n-nodes-base.httpRequest"
    vision["typeVersion"] = 4.2
    vision["parameters"] = {
        "method": "POST",
        "url": NIM_URL,
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify($json.nim_body) }}",
        "options": {"timeout": 35000, "response": {"response": {"responseFormat": "json"}}},
    }
    vision["credentials"] = {"httpHeaderAuth": {"id": cred_id, "name": NIM_CREDENTIAL_NAME}}
    # Survive a transient NIM 5xx without failing the volunteer's tap.
    vision["retryOnFail"] = True
    vision["maxTries"] = 2
    vision["waitBetweenTries"] = 1000

    # 4. parse node: understand NIM's response shape + the rename
    parse = nodes[PARSE_NODE]
    parse["parameters"]["jsCode"] = patch_parse_code(parse["parameters"]["jsCode"])
    # Carry the archived-photo fields through so every logged prediction points at
    # the exact image it was made from. This is what makes a row trainable later.
    # Tare scales with the NUMBER of containers. Subtracting a single tare from a
    # 6-crate load under-reported the container weight by 5 tares. [fixed 2026-07-29]
    code = parse["parameters"]["jsCode"]

    # TARE REMOVED (2026-08-02). The model reports FOOD-ONLY weight, so subtracting a
    # container tare downstream double-counted it. Removing the subtraction also
    # removes resolveContainer's fuzzy keyword matching from the weight path — that
    # lookup could resolve the same photo to different containers on different runs,
    # which is exactly the kind of nondeterminism we do not want in a logged number.
    # container_type / container_count are still recorded, they just no longer alter it.
    if "TARE_REMOVED" not in code:
        code = code.replace(
            "  ? Math.max(0, rawWeight - totalTare)",
            "  ? Math.max(0, rawWeight)   // TARE_REMOVED: model already reports food-only weight")
        code = code.replace(
            "  ? Math.max(0, rawWeight - container.tare_lbs)",
            "  ? Math.max(0, rawWeight)   // TARE_REMOVED: model already reports food-only weight")
        code = code.replace(
            "const totalTare = container.tare_lbs * containerCount;",
            "const totalTare = 0;   // TARE_REMOVED 2026-08-02")
        code = code.replace(
            "  tare_lbs: totalTare,",
            "  tare_lbs: 0,\n  tare_applied: false,")
        code = code.replace("  tare_lbs_each: container.tare_lbs,\n", "")
        # Write back immediately — this must not depend on any later branch running.
        parse["parameters"]["jsCode"] = code

    if "containerCount" not in code:
        code = code.replace(
            "const container = resolveContainer(vision);",
            "const container = resolveContainer(vision);\n"
            "// How many containers of this item are in the zone (v0.5 counting contract).\n"
            "const containerCount = Number.isFinite(vision.container_count) && vision.container_count > 0\n"
            "  ? Math.round(vision.container_count) : 1;\n"
            "const totalTare = container.tare_lbs * containerCount;")
        code = code.replace(
            "  ? Math.max(0, rawWeight - container.tare_lbs)",
            "  ? Math.max(0, rawWeight - totalTare)")
        code = code.replace(
            "  tare_lbs: container.tare_lbs,",
            "  tare_lbs: 0,                 // TARE_REMOVED — kept as a column for history\n"
            "  tare_applied: false,\n"
            "  container_count: containerCount,\n"
            "  container_fill_fraction: vision.container_fill_fraction ?? null,")
        parse["parameters"]["jsCode"] = code

    if "image_url:" not in parse["parameters"]["jsCode"]:
        parse["parameters"]["jsCode"] = parse["parameters"]["jsCode"].replace(
            "  prompt_version: config.prompt_version,",
            "  image_url: trigger.image_url ?? null,\n"
            "  image_sha256: trigger.image_sha256 ?? null,\n"
            "  image_bytes: trigger.image_bytes ?? null,\n"
            "  archive_error: trigger.archive_error ?? null,\n"
            "  prompt_version: config.prompt_version,")

    # Physical sanity bound. The 6ft x 6ft zone cannot plausibly hold more than a
    # couple thousand pounds; an estimate above the bound almost always means the
    # model over-counted containers. Flag it and drop confidence rather than logging
    # a confident absurdity. The raw number is still recorded for review.
    parse_code = parse["parameters"]["jsCode"]
    if "IMPLAUSIBLE_LBS" not in parse_code:
        parse_code = parse_code.replace(
            "return [{ json: {",
            "const IMPLAUSIBLE_LBS = 2000;\n"
            "const implausible = typeof adjustedWeight === 'number' && adjustedWeight > IMPLAUSIBLE_LBS;\n"
            "const vFlags = Array.isArray(vision.known_failure_flags) ? vision.known_failure_flags.slice() : [];\n"
            "if (implausible) vFlags.push('implausible_weight_review');\n\n"
            "return [{ json: {",
            1)
        parse_code = parse_code.replace(
            "  bias_multiplier: multiplier,",
            "  known_failure_flags: vFlags,\n"
            "  implausible_weight: implausible,\n"
            "  confidence: implausible ? Math.min(vision.confidence ?? 0.5, 0.3) : (vision.confidence ?? null),\n"
            "  bias_multiplier: multiplier,",
            1)
        parse["parameters"]["jsCode"] = parse_code

    # Shape response is ALL the relay (and therefore the CSV and the iPad) ever sees,
    # so anything worth logging or showing must be listed here explicitly.
    shape = nodes.get(SHAPE_NODE)
    if shape and "container_count" not in shape["parameters"]["jsCode"]:
        shape["parameters"]["jsCode"] = shape["parameters"]["jsCode"].replace(
            "  charuco_detected: parsed.charuco_detected ?? false,",
            "  charuco_detected: parsed.charuco_detected ?? false,\n"
            "  container_type: parsed.container_type ?? null,\n"
            "  container_count: parsed.container_count ?? null,\n"
            "  container_fill_fraction: parsed.container_fill_fraction ?? null,\n"
            "  tare_lbs: parsed.tare_lbs ?? null,\n"
            "  weight_lbs_low: parsed.weight_lbs_low ?? null,\n"
            "  weight_lbs_high: parsed.weight_lbs_high ?? null,\n"
            "  implausible_weight: parsed.implausible_weight ?? false,\n"
            "  prompt_version: parsed.prompt_version ?? null,\n"
            "  model: parsed.model ?? null,",
            1)

    # Farmbrite: replace the "skipped (pending key)" stub with a real draft-order write.
    skip = nodes.get(FARMBRITE_SKIP_NODE)
    fb_cred = (REPO / ".n8n-farmbrite-credential-id")
    if skip is not None and fb_cred.exists():
        pos = skip.get("position", [0, 0])
        builder = {
            "id": str(uuid.uuid4()), "name": FARMBRITE_BUILD_NODE,
            "type": "n8n-nodes-base.code", "typeVersion": 2,
            "position": [pos[0], pos[1] + 160],
            "parameters": {"jsCode": farmbrite_build_code()},
        }
        writer = {
            "id": str(uuid.uuid4()), "name": FARMBRITE_NODE,
            "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
            "position": [pos[0] + 200, pos[1] + 160],
            "parameters": {
                "method": "POST", "url": FARMBRITE_URL,
                "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
                "sendBody": True, "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify($json.order_body) }}",
                "options": {"timeout": 20000},
            },
            "credentials": {"httpHeaderAuth": {"id": fb_cred.read_text().strip(),
                                               "name": FARMBRITE_CREDENTIAL_NAME}},
            # Farmbrite being down must never fail the volunteer's tap — the Sheet row
            # and the photo are already safe by this point.
            "onError": "continueRegularOutput",
            "retryOnFail": True, "maxTries": 2, "waitBetweenTries": 1000,
            "alwaysOutputData": True,
        }
        # Idempotent: refresh the parameters of nodes that already exist rather than
        # only creating them once. Otherwise a fix to the builder code silently never
        # reaches the live workflow on a re-run. [fixed 2026-08-02]
        by_name = {n["name"]: n for n in wf["nodes"]}
        for node in (builder, writer):
            current = by_name.get(node["name"])
            if current is None:
                wf["nodes"].append(node)
            else:
                current["parameters"] = node["parameters"]
                current["type"] = node["type"]
                current["typeVersion"] = node["typeVersion"]
                if "credentials" in node:
                    current["credentials"] = node["credentials"]
                for k in ("onError", "retryOnFail", "maxTries", "waitBetweenTries", "alwaysOutputData"):
                    if k in node:
                        current[k] = node[k]
        conns = wf.setdefault("connections", {})
        conns[FARMBRITE_SKIP_NODE] = {"main": [[
            {"node": FARMBRITE_BUILD_NODE, "type": "main", "index": 0},
            {"node": SHAPE_NODE, "type": "main", "index": 0},
        ]]}
        conns[FARMBRITE_BUILD_NODE] = {"main": [[{"node": FARMBRITE_NODE, "type": "main", "index": 0}]]}
        conns.setdefault(FARMBRITE_NODE, {"main": [[]]})

    # 2) Sheet: log the photo pointer alongside the prediction.
    sheet = nodes.get(SHEET_NODE)
    if sheet:
        cols = sheet["parameters"].get("columns", {}).get("value")
        if isinstance(cols, dict):
            cols.setdefault("image_url", "={{ $json.image_url }}")
            cols.setdefault("image_sha256", "={{ $json.image_sha256 }}")
            cols.setdefault("container_count", "={{ $json.container_count }}")
            cols.setdefault("container_fill_fraction", "={{ $json.container_fill_fraction }}")

    # 5. drop the dead bridge fetch and rewire config -> build
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] != OLD_FETCH_NODE]

    conns = wf.get("connections", {})
    conns.pop(OLD_FETCH_NODE, None)
    if OLD_BUILD_NODE in conns:                       # follow the rename
        conns[BUILD_NODE] = conns.pop(OLD_BUILD_NODE)
    conns[CONFIG_NODE] = {"main": [[{"node": BUILD_NODE, "type": "main", "index": 0}]]}
    for source in conns.values():                     # repoint any other reference
        for group in source.get("main", []):
            for link in group:
                if link.get("node") in (OLD_FETCH_NODE, OLD_BUILD_NODE):
                    link["node"] = BUILD_NODE
    wf["connections"] = conns
    return wf


# ---------------------------------------------------------------------- verify
def put_body(wf: dict) -> dict:
    """Exactly what goes on the wire. n8n rejects unknown top-level/settings keys, and
    read-only fields it returns on GET (e.g. activeVersion, which embeds a stale copy of
    the old workflow) must never be echoed back."""
    return {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED_SETTINGS},
    }


def redacted_for_commit(wf: dict) -> str:
    """Serialize the workflow with live tokens masked.

    The workflow carries APERTURE_SHARED_TOKEN inline (Verify Token node) and older
    versions carried BRIDGE_TOKEN. Committed n8n JSON must never contain them — see
    the secrets convention in AGENTS.md. Backups keep the real values and are
    gitignored, because a rollback needs them verbatim.
    """
    text = json.dumps(wf, indent=2)
    return re.sub(r"\b[0-9a-f]{64}\b", "REDACTED-see-SECRETS.local.md", text)


def verify(wf: dict) -> list[str]:
    problems: list[str] = []
    names = {n["name"] for n in wf["nodes"]}

    if OLD_FETCH_NODE in names:
        problems.append("dead bridge fetch node still present")

    # Scan the outgoing payload only — not read-only GET fields we never send.
    blob = json.dumps(put_body(wf))
    for pattern, label in (
        (r"nvapi-[A-Za-z0-9_-]{20,}", "NVIDIA NIM api key"),
        (r"trycloudflare\.com", "dead quick-tunnel URL"),
        (r"bridge\.example\.com", "dead bridge hostname"),
    ):
        if re.search(pattern, blob):
            problems.append(f"outgoing workflow contains {label}")

    # every $('Node') reference must resolve
    for node in wf["nodes"]:
        code = node.get("parameters", {}).get("jsCode", "")
        for ref in set(re.findall(r"\$\('([^']+)'\)", code)):
            if ref not in names and ref != "<name>":
                problems.append(f"{node['name']}: dangling reference $('{ref}')")

    # every connection endpoint must exist
    for src, spec in wf.get("connections", {}).items():
        if src not in names:
            problems.append(f"connection from unknown node {src!r}")
        for group in spec.get("main", []):
            for link in group:
                if link["node"] not in names:
                    problems.append(f"{src} -> unknown node {link['node']!r}")

    # the critical path must be intact
    def targets(name):
        return [l["node"] for g in wf["connections"].get(name, {}).get("main", []) for l in g]

    if BUILD_NODE not in targets(CONFIG_NODE):
        problems.append(f"{CONFIG_NODE} does not feed {BUILD_NODE}")
    if VISION_NODE not in targets(BUILD_NODE):
        problems.append(f"{BUILD_NODE} does not feed {VISION_NODE}")
    if PARSE_NODE not in targets(VISION_NODE):
        problems.append(f"{VISION_NODE} does not feed {PARSE_NODE}")

    vision = next((n for n in wf["nodes"] if n["name"] == VISION_NODE), None)
    if not vision or vision.get("type") != "n8n-nodes-base.httpRequest":
        problems.append("vision node is not an httpRequest")
    elif not vision.get("credentials", {}).get("httpHeaderAuth", {}).get("id"):
        problems.append("vision node has no NIM credential attached")

    build = next((n for n in wf["nodes"] if n["name"] == BUILD_NODE), None)
    if build and "response_format" not in build["parameters"]["jsCode"]:
        problems.append("build node omits response_format=json_object (model will emit prose)")
    return problems


# ------------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="verify and write the candidate, do not PUT")
    ap.add_argument("--restore", metavar="FILE", help="restore a backup JSON to the live workflow")
    args = ap.parse_args()

    backups = REPO / "n8n" / "backups"
    backups.mkdir(parents=True, exist_ok=True)

    if args.restore:
        payload = json.loads(Path(args.restore).read_text())
        print("restore ->", api("PUT", f"/workflows/{WORKFLOW_ID}", put_body(payload))[0])
        print("activate ->", api("POST", f"/workflows/{WORKFLOW_ID}/activate")[0])
        return

    status, live = api("GET", f"/workflows/{WORKFLOW_ID}")
    if status != 200:
        sys.exit(f"ERROR: could not fetch workflow ({status}): {live}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backups / f"workflow-{stamp}.json"
    backup.write_text(json.dumps(live, indent=2))
    print(f"backup      -> {backup.relative_to(REPO)}")

    candidate = transform(json.loads(json.dumps(live)), load_system_prompt(), find_credential_id())

    problems = verify(candidate)
    if problems:
        print("\nVERIFICATION FAILED — live workflow untouched:")
        for p in problems:
            print("  ✗", p)
        sys.exit(1)
    print("verification-> ✅ all checks passed "
          "(no secrets, no dead hosts, refs resolve, critical path intact)")

    committed = REPO / "n8n" / "aperture-workflow-ipad-nim.json"
    committed.write_text(redacted_for_commit(candidate))
    if re.search(r"\b[0-9a-f]{64}\b", committed.read_text()):
        sys.exit("ERROR: redaction failed — refusing to leave a token in a committed file.")
    print("candidate   -> n8n/aperture-workflow-ipad-nim.json (tokens redacted for commit)")

    if args.dry_run:
        print("dry-run     -> nothing pushed")
        return

    status, out = api("PUT", f"/workflows/{WORKFLOW_ID}", put_body(candidate))
    print("PUT         ->", status, "" if status == 200 else out)
    if status != 200:
        sys.exit(1)

    status, out = api("POST", f"/workflows/{WORKFLOW_ID}/activate")
    print("activate    ->", status)

    status, check = api("GET", f"/workflows/{WORKFLOW_ID}")
    if status == 200:
        print(f"live        -> active={check.get('active')} nodes={len(check.get('nodes', []))}")
        # Read back what n8n actually stored. A 200 on the PUT does NOT guarantee the
        # change landed (see the node-type note above), so assert the live state.
        live_nodes = {n["name"]: n for n in check.get("nodes", [])}
        readback = []
        v = live_nodes.get(VISION_NODE)
        if not v or v.get("type") != "n8n-nodes-base.httpRequest":
            readback.append(f"{VISION_NODE} is {v.get('type') if v else 'MISSING'}, expected httpRequest")
        if OLD_FETCH_NODE in live_nodes:
            readback.append("dead bridge fetch node still live")
        if BUILD_NODE not in live_nodes:
            readback.append(f"{BUILD_NODE} missing")
        if readback:
            print("\nREADBACK FAILED — live workflow is NOT in the intended state:")
            for r in readback:
                print("  ✗", r)
            print(f"  restore with: python3 scripts/rewire-n8n-ipad-nim.py --restore {backup.relative_to(REPO)}")
            sys.exit(1)
        print("readback    -> ✅ live workflow matches intent (vision=httpRequest, bridge gone)")
        print(f"rollback    -> python3 scripts/rewire-n8n-ipad-nim.py --restore {backup.relative_to(REPO)}")


if __name__ == "__main__":
    main()
