# n8n Setup — Aperture

The workflow is `aperture-workflow.json`. Import it, then fill in the slots.

## 1. Import

In n8n Cloud (or self-hosted):

1. Workflows → **Import from File** → `aperture-workflow.json`
2. Leave it **inactive** until all credentials below are connected.

## 2. Environment variables (n8n → Settings → Variables)

Per [feedback_n8n_native_nodes] use native nodes + credentials. The workflow
references these env vars via `{{ $env.NAME }}`:

| Variable | Purpose | Where to get it |
|---|---|---|
| `APERTURE_SHARED_TOKEN` | Must match the value in Vercel env. Rejects unauthenticated callers. | `openssl rand -hex 32` |
| `HIKVISION_CAMERA_URL` | HTTPS URL that returns a JPEG snapshot from the camera. | See `../camera-access/README.md` — pick an option, paste the resulting URL here. |
| `FARMBRITE_API_BASE` | `https://api.farmbrite.com/v1` (confirmed via https://developers.farmbrite.com/docs/). Leave blank to skip Farmbrite writes. | Official docs |
| `FARMBRITE_INVENTORY_TYPE_ID` | ID of the inventory_type to append donations to. Auto-created as "Aperture Donations" by the probe script. | `./scripts/discover-farmbrite-endpoint.sh` |
| `FARMBRITE_LOCATION_ID` | ID of the Farmbrite location (warehouse/farm) to credit. | Same script lists existing locations |
| `APERTURE_LOG_SHEET_ID` | Google Sheet ID for the running donation log (fire-and-forget parallel to Farmbrite). | Create the sheet, copy ID from its URL |

## 3. Credentials (n8n → Credentials)

Create three credentials and wire them into the matching nodes:

1. **Hikvision Camera (HTTP Digest Auth)**
   - User/pass set during first-boot of the camera (keep these in 1Password).
2. **OpenAI API**
   - API key from `platform.openai.com`. Model `gpt-4o` in the Vision node.
   - Swap to Anthropic Claude by changing the node — see `prompts/weight-estimation.md`.
3. **Farmbrite API Key (HTTP Header Auth)** — *optional at first-run*
   - If you don't have the key yet: skip this credential entirely AND leave
     the `FARMBRITE_API_*` env vars blank. The workflow detects the missing
     config, skips the Farmbrite write, and still returns weight + item type
     to the iPad. Every execution is preserved in n8n execution history —
     backfill to Farmbrite once the key is wired.
   - Header name: confirm via `./scripts/discover-farmbrite-endpoint.sh`.
     Typically `Authorization: Bearer <key>` or `X-Api-Key: <key>`.

## 4. Paste the vision prompt

Open the **Vision: weight estimate** node → "System Message" field → paste the
entirety of `prompts/weight-estimation.md` from the `## System prompt` header
through end-of-file. (Or move it to a Set node if you prefer keeping prompt
in workflow JSON.)

## 5. Activate + test

1. Activate the workflow.
2. Copy the Production Webhook URL → paste into Vercel env as `N8N_WEBHOOK_URL`.
3. `curl -X POST -H "X-Aperture-Token: $APERTURE_SHARED_TOKEN" \
   -H "Content-Type: application/json" -d '{"description":"curl test"}' \
   $N8N_WEBHOOK_URL`
4. Verify: camera snapshot appears in execution log, vision JSON is valid,
   Farmbrite returns 2xx, response shape matches what the PWA expects.

## 6. Per-run observability

Each execution logs the prompt version, camera snapshot (first 1KB), and
Farmbrite response. The Phase 2 training loop reads from this execution
history to compute residuals against ground-truth weights.
