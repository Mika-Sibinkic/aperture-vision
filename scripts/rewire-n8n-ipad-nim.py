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
NIM_MODEL = "meta/llama-3.2-90b-vision-instruct"
PROMPT_VERSION = "v0.4-nim"
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
