# n8n workflow

Import this one: `aperture-workflow-ipad-nim.json`. It is the live 17-node workflow.
`scripts/rewire-n8n-ipad-nim.py` generates it. The script reads the live workflow over
the n8n API, rewires it for the iPad and NVIDIA NIM, checks it, writes the redacted
copy here, then PUTs it back (`--dry-run` stops before the PUT, `--restore <backup>`
rolls back).

The other six files are history. Scripts and old runbooks still name some of them, so
they stay where they are. Every one of them fetches the camera frame through the
camera bridge, which the iPad path no longer uses.

| File | Nodes | How it differs |
|---|---|---|
| `aperture-workflow.json` | 19 | First build (April 2026): bridge fetch, OpenAI vision, optional bias and density fetches |
| `aperture-workflow-starter.json` | 19 | Same nodes, named "STARTER-COMPATIBLE v1.1" |
| `aperture-workflow-MERGED.json` | 19 | Same nodes, named "MERGED" |
| `aperture-workflow-CLEAN.json` | 17 | First build without the two optional fetches |
| `aperture-workflow-LIVE-snapshot.json` | 16 | Bridge-era live copy, no Farmbrite write |
| `aperture-workflow-LIVE-v2.json` | 16 | Bridge-era live copy with a 401 response, no Farmbrite write |

The legacy PWA in `app/page.tsx` posts no image, so it only works against one of these
bridge-era workflows.

## Set it up

Use native n8n nodes and n8n credentials. Keys never go in the workflow JSON.

1. Workflows → **Import from File** → `aperture-workflow-ipad-nim.json`. Leave it
   inactive.
2. In **Verify Token**, replace `REDACTED-see-SECRETS.local.md` with your shared
   token. It must match `APERTURE_SHARED_TOKEN` in Vercel (`openssl rand -hex 32`).
3. Create the credentials and attach them:
   - `NVIDIA NIM (Aperture)`: Header Auth, `Authorization: Bearer <NIM key>`, on
     **Vision: weight estimate**.
   - Google Sheets OAuth2, on **Append to Google Sheet**. Put your sheet ID in place
     of `<google-sheet-id>`. The tab is named `Donations`.
   - `Farmbrite (Aperture)`: Header Auth, on **Farmbrite: log order**. Optional.
4. Farmbrite is optional. Set `FARMBRITE_API_BASE`, `FARMBRITE_INVENTORY_TYPE_ID` and
   `FARMBRITE_LOCATION_ID` in n8n variables to turn it on. With any of them blank,
   **Guard: Farmbrite configured** skips the write and the tap still returns a
   weight. `scripts/farmbrite-setup.py` finds the IDs. The product map in
   **Build Farmbrite order** comes from `PRODUCT_MAP` in the rewire script. It is
   Cul2vate's catalogue, so replace it with yours.
5. Paste the prompt. **Build vision request** holds the system prompt as a string.
   Its source is `prompts/weight-estimation.md`, between `## SYSTEM PROMPT` and
   `## END SYSTEM PROMPT`. The rewire script does this for you.
6. Activate. Copy the production webhook URL into Vercel as `N8N_WEBHOOK_URL`.

## Check it

The workflow refuses a tap without a real frame, so a bare `curl` with only a
description fails at **Build vision request**. Post a real JPEG instead:

```bash
python3 scripts/vision-regression-test.py --e2e
```

That goes through the live relay and writes real records: a Sheet row, a Farmbrite
draft and an archived photo. `/api/void` (the iPad's undo) deletes the draft and drops
the record from the CSV export. The Sheet row stays.
