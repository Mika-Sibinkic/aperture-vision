# n8n workflow

Import `aperture-workflow-ipad-nim.json`. It has 16 nodes. The live workflow has 17,
and none of the changes from 2026-11-11 below are deployed:

- A Farmbrite fix. It adds **Farmbrite: has order?**, stops generic words like
  "potatoes" from matching a specific variety (a word still matches when exactly one
  product contains it, so "carrot" finds Carrots), matches Ministry products by the
  name after "Ministry " ("eggs" finds Ministry Eggs), skips November-May loads that
  have no Seasonal bucket, and returns `farmbrite_skipped_reason`. It deletes the dead
  **Farmbrite skipped (pending key)** stub and the disabled **Guard: Farmbrite
  configured**, and drops the always-false `farmbrite_pending` and the duplicate
  `farmbrite_id` from the response.
- Prompt v0.9-board, which gives the board's real 4 in square size. Live still runs
  v0.8-scene, which says 6 in.
- The weight node (**Parse vision + tare + bias**, name kept so references hold) is
  written whole by the rewire script. It logs the model's `container_type` as it came;
  live still rewrites it from keywords in the notes.

Until they are pushed, the live workflow has none of them.

`scripts/rewire-n8n-ipad-nim.py` generates the file. It reads the live workflow over
the n8n API, rewires it for the iPad and NVIDIA NIM, checks it, writes the redacted
copy here (name, nodes, connections and settings only), then PUTs it back
(`--dry-run` stops before the PUT, `--restore <backup>` rolls back). The redacted copy
has placeholders for the shared token, every credential id and the Sheet id; the
script refuses to write it otherwise, and CI checks it. It needs `N8N_BASE_URL`,
`N8N_API_KEY` and `N8N_WORKFLOW_ID` in the environment.

Nine Sheet columns are constants kept for Cul2vate's existing Sheet: `tare_lbs`,
`bias_multiplier`, `density_used`, `density_source`, `scale_reading_lbs`,
`scale_confidence`, `true_weight_lbs`, `ground_truth_source` and
`residual_vs_scale_lbs`. Nothing measures them. A fork can delete them from the
template, the **Append to Google Sheet** mapping and `parse_vision_code()`.

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
4. Farmbrite runs on every tap with a positive weight. No n8n variable turns it off.
   To skip Farmbrite, disable **Farmbrite: log order**. To use it, replace `PRODUCT_MAP` in
   `scripts/rewire-n8n-ipad-nim.py` with your products, then run the script. Edit it
   there, not in **Build Farmbrite order**: the next rewire overwrites the node.
   Farmbrite lists products at `GET https://api.farmbrite.com/v1/products` with the
   Bearer token (`docs/OPERATIONS.md` §8).
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
