# Aperture: accuracy roadmap (candidate methods, none presumed)

> State: directional, decisions not made · Optionality: HIGH, this doc exists to keep it that way · Open to Change: yes, recursively. Goal: **≥95% accuracy, reliably**, on real items at real sites.
> Principle (applies to virtually all Aperture plans and technicals): training data is ONE method, not THE method. Every plan doc should treat accuracy approaches as an open portfolio, gated by per-site evidence, not as a settled pipeline.

## Candidate methods

| # | Method | What it is | Where it applies | Expected lift | Cost/risk |
|---|---|---|---|---|---|
| 1 | **SKU scanning / lookup** | Scan or detect a SKU/UPC; pull known unit weight + dimensions from a product DB; vision then only counts units or verifies | Items with known, stable SKUs (retail-donated goods, parcel/fulfillment, packaged food). NOT new/unknown/loose items | Potentially the biggest single jump toward ≥95% reliable; replaces estimation with lookup for the covered share of volume | Needs SKU→weight database (vendor data, GS1, or accumulated); coverage % varies by site; loose produce uncovered |
| 2 | **Site training data** | Ground-truth (scale weight + photo) pairs from the actual dock; fine-tune/correct the image model | All items, especially loose produce where SKU doesn't exist | Proven once (Branch era); magnitude on Cul2vate produce unknown until measured | Slow to collect; per-site effort; drift as seasons/items change |
| 3 | **Calibration tightening** | ChArUco board geometry, camera pose, fixed-zone discipline (already partly built) | Every deployment | Foundation; reduces variance, doesn't fix density errors | Cheap; mostly done; verify per install |
| 4 | **Category density priors** | Per-category weight/volume tables (tomatoes vs. canned goods), site-seasonal | Loose/variable items | Moderate; compounds with #2 | Needs category classifier to be right first |
| 5 | **Label/text OCR** | Read printed weights ("5 lb bag"), counts, and product names off packaging | Packaged items without scannable SKU or where camera can't resolve barcode | Similar character to #1 with lower reliability | OCR errors; angle/occlusion dependent |
| 6 | **Multi-angle / multi-frame** | 2-3 captures per item or short burst; aggregate estimates | High-value or irregular items | Variance reduction | UX cost at the dock; more compute |
| 7 | **Scale-in-the-loop verification** | Keep a scale for a sampled fraction; auto-compare to build correction factors + live accuracy stats | Any site willing to keep one scale | Turns accuracy from a claim into a measured, self-improving number | Partial bottleneck retained; sampling design needed |
| 8 | **Hybrid routing** | Classifier decides per item: SKU-covered → lookup (#1); packaged-no-SKU → OCR (#5); loose → vision + priors (#2+#4); low-confidence → flag/manual | All sites; this is the probable end-state architecture | The portfolio's compounding payoff | Most engineering; only worth it once 2+ methods exist |

## How to choose (per site, per item mix)

1. Measure the item-mix split first: what % of weekly volume is SKU-known vs. packaged-no-SKU vs. loose? (At Cul2vate: heavy loose-produce share → #2/#4 matter; retail-donation streams → #1 could cover a big share fast.)
2. Estimate lift × coverage for each method against that split.
3. Build the cheapest method that moves the site's blended accuracy most; re-measure; repeat. Do not default to "more training data" without doing this arithmetic.

## Implications for existing docs (the recursive bit)

- `docs/BUSINESS.md` plan step 1 ("train the model, the whole ballgame") is **softened**: collecting ground truth is still step 1 because it measures today's baseline AND feeds methods #2/#7, but the route to ≥95% may well run through #1 (SKU) where applicable.
- `docs/deals/enterpriseco/` + conveyor brief: EnterpriseCo volume is largely SKU/barcode-rich parcels; method #1 + #3 likely dominates there, which materially de-risks that pitch (lookup, not estimation, for most items). Update 05-architecture / 13-buildout when re-engaging.
- `SPEC.md` / `prompts/`: vision prompt should eventually emit `sku_candidate`, `label_text`, and `confidence` fields to enable hybrid routing (#8).
- Anyone editing a plan doc: if it assumes a single accuracy method, fix it and cite this file.
