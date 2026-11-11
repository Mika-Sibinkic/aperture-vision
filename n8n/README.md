# n8n workflow

Import `aperture-workflow-ipad-nim.json`. It has 18 nodes: the 17-node live workflow
plus one fix from 2026-11-11 that is not deployed yet. That fix adds **Farmbrite: has
order?**, stops generic words like "potatoes" from matching a specific variety, skips
November-May loads that have no Seasonal bucket, and returns `farmbrite_skipped_reason`.
Until it is pushed, the live workflow has none of those.

`scripts/rewire-n8n-ipad-nim.py` generates the file. It reads the live workflow over
the n8n API, rewires it for the iPad and NVIDIA NIM, checks it, writes the redacted
copy here (name, nodes, connections and settings only), then PUTs it back
(`--dry-run` stops before the PUT, `--restore <backup>` rolls back).

The bridge-era workflows are in git history: `git log --all -- n8n/`. Every one of them
fetched the frame through a camera bridge that no longer runs. The legacy PWA in
`app/page.tsx` posts no image, so it only worked against those.

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
   - `Farmbrite (Aperture)`: Header Auth, on **Farmbrite: log order**.
4. Farmbrite runs on every tap with a positive weight. No n8n variable turns it off:
   **Guard: Farmbrite configured** is disabled and nothing connects to it. To skip
   Farmbrite, disable **Farmbrite: log order**. To use it, replace the `PRODUCTS` map in
   **Build Farmbrite order** first. It holds Cul2vate's product IDs, and it comes from
   `PRODUCT_MAP` in the rewire script.
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

That goes through the live relay and writes real records, then voids each one through
`/api/void`. Voiding deletes the Farmbrite draft (when Vercel has `FARMBRITE_API_KEY`)
and drops the record from the CSV export. The Sheet row stays, labeled as a regression test. Once
`APERTURE_DEVICE_TOKEN` is set, export it before you run the probe.
