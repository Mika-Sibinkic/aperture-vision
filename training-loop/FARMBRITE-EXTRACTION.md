# Farmbrite Historical Data Extraction — Playbook

**Goal:** pull Cul2vate's complete historical records out of Ava's admin
Farmbrite account for use as Aperture training data (per
`README.md` §"Data requirements" and §"Sources" #3 — gold standard).

**Constraint:** Farmbrite's public API is beta and requires a support
request for an API key. We do not wait on that. We extract via the UI
exports in parallel, then upgrade to API once the key arrives.

## What we ultimately need (training fields)

| Field            | Required | Where it lives in Farmbrite                |
|------------------|----------|--------------------------------------------|
| `weight_lbs`     | ✅       | Harvest records (qty + unit) ; Transactions |
| `item_type`      | ✅       | Crop name, Inventory Type, Product name    |
| `source_url`     | ✅       | Photo URL (UI download or API `/photos`)   |
| `image_bytes`    | ✅       | Photos attached to crops/harvests/items    |
| date / location  | nice     | All record types carry these               |

## Three-track extraction

### Track A — CSV exports (do FIRST, no support ticket needed)

**Sidebar nav names (verified from Cul2vate's actual UI 2026-04-29):**
Schedule, Tasks, Livestock, **Plantings**, **Resources**, Accounting,
Market (Dashboard/Products/Orders/Settings), Contacts, Farm Map,
Climate, Reports.

**There is no top-level "Crops" or "Inventory" — that data lives under
Plantings and Resources respectively.**

Every module has an **Actions menu** (`...` button next to the green
"Create New" button) → **Download All Records**. Pull these in order:

1. **Reports → Crop Harvest Report** — run with no filter, all years →
   Export CSV → `01_harvest_report.csv` (this is the richest single
   file — weight × crop × date × batch/trace numbers)
2. **Plantings → Actions → Download All Records** → `02_plantings.csv`
3. **Plantings → click into any planting → Harvests tab → Actions** —
   if a per-planting Harvests CSV exists separately from #1, grab one
   sample to compare schemas → `03_harvests_sample.csv`
4. **Resources → Actions → Download All Records** → `04_resources.csv`
   (this covers inventory/equipment/storage)
5. **Resources → Inventory Transactions → Download All** (if surfaced
   as its own list view) → `05_inventory_transactions.csv`
6. **Market → Products → Actions → Download All Records** →
   `06_products.csv` *(skip if Products is greyed out)*
7. **Market → Orders → Actions → Download All Records** →
   `07_orders.csv` (the "Orders/Invoices" screen confirmed live)
8. **Accounting → Transactions → Actions → Download All Records** →
   `08_accounting_transactions.csv` *(skip if Accounting is greyed out
   — that means the user role lacks financial access)*
9. **Contacts → Actions → Download All Records** → `09_contacts.csv`
10. **Reports → Custom Reports** — if Ava built any, export each →
    `99_custom_reports/<name>.csv`. Custom reports often join
    harvest × product × weight × date in ways the raw CSVs don't.

Skip: Livestock (Cul2vate doesn't log animals), Equipment (covered by
Resources), Schedule/Tasks (operational, not training data).

Save each file into:
```
training-loop/farmbrite_export_2026-04-29/
  ├── 01_harvests.csv
  ├── 02_crops.csv
  ├── 03_inventory_types.csv
  ├── 04_inventory_transactions.csv
  ├── 05_products.csv
  ├── 06_accounting_transactions.csv
  ├── 07_contacts.csv
  └── 99_custom_reports/
```

### Track B — Photo audit (do SECOND, while still logged in)

CSV exports do **not** include photos. Before requesting an API key, we
need to know if photos exist at all — that determines whether the data
is gold standard (image + weight) or silver (weight only).

While Ava is in Crops, click into 3-5 random crop records and check:

- Is there a photo on the record? (Camera/photo tab.)
- Are photos on **Harvest** entries individually, or only on the parent
  crop? (This matters — per-harvest photos = a real training row.)
- Same check on Inventory Types and Products.

Document findings in `training-loop/farmbrite_export_2026-04-29/PHOTO-AUDIT.md`:

```markdown
## Photo presence in Farmbrite (Cul2vate)
- Crops: <yes/no>, count out of 5 sampled, typical (1 hero / many / per-harvest)
- Harvests: <yes/no>
- Inventory Types: <yes/no>
- Products: <yes/no>
- Accounting Transactions: <yes/no>
```

If photos are absent on harvests but present on crops, the training set
becomes "one crop image × N weight rows" — usable but lower-quality.
Note this in the audit so the scraper handles it correctly.

### Track C — API access (do THIRD, takes 1-3 business days)

**Prerequisite: confirmed Admin role.** Only Admins can request API
keys. If admin verification fails (see "Admin verification" section
below), the client contact — the actual account owner — has to do this part.

Once confirmed Admin:

1. Click profile avatar (top-right) → **My Profile** / **User Profile**
2. Find the link "Request API Access" or similar — Farmbrite docs say
   it lives on the User Profile page
3. Submit the request. Reason text:
   > "Read-only access to harvest, inventory, product, and photo records
   > for an internal analytics integration. Read-only is sufficient."
4. Once granted, store the key in `business-framework/.env` as:
   ```
   FARMBRITE_API_KEY=...
   FARMBRITE_BASE_URL=https://api.farmbrite.com/v1
   ```

## Admin verification (do this BEFORE Track C)

Per Farmbrite's role docs, only the **Admin** role can manage billing,
all settings, and request API access. Other roles (Operations Manager,
Farmhand, Accountant, Shop Manager, Auditor) all have restrictions.

**Greyed-out menu items are a permission signal**, not a styling
artifact. If Accounting is greyed → role likely Farmhand. If Market
sub-items are greyed → role likely lacks Market access.

Three definitive tests (run in order, stop at first failure):

| Test | Path | Pass = role |
|------|------|-------------|
| A | Settings → Subscription / Billing | **Admin only** |
| B | Settings → Users → "New User" button visible | Admin or Ops Mgr |
| C | Profile → "Request API Access" / "API Keys" link | **Admin only** |

If Test A fails: stop Track C. Forward this finding to the client contact (account
owner) so he either elevates Ava's role to Admin, or runs the API
request himself. Tracks A + B still work for any role on the modules
the user can see.

Then run the photo puller:

```bash
python training-loop/scraper.py --source farmbrite --since 2023-01-01
```

(Update `scraper.py` to add a `farmbrite` source mode that paginates
`GET /photos`, `GET /crops/{id}/harvests`, joins by ID, downloads each
photo to `images/<sha256>.jpg`, writes label JSON to `labels/<sha256>.json`.)

## API reference (for Track C)

- Base: `https://api.farmbrite.com/v1`
- Auth header: `api_key: <KEY>` *or* `Authorization: Bearer <KEY>`
- Pagination: `?page=N&limit=100` (max 100/page)

Endpoints we'll use:
```
GET /crops                                 # list all crop plantings
GET /crops/{id}/harvests                   # weight + date per harvest
GET /inventory_types                       # master list
GET /inventory_types/{id}/inventory        # line items in a type
GET /transactions                          # accounting incl. in-kind
GET /photos                                # all photos w/ resource refs
GET /animals (skip — Cul2vate doesn't have)
```

Pull strategy (full historical sweep, single run):

```python
# pseudocode for scraper.py farmbrite mode
crops = paginate("/crops")
for c in crops:
    harvests = paginate(f"/crops/{c.id}/harvests")
    photos = [p for p in all_photos if p.resource_id == c.id]
    for h in harvests:
        if not photos: skip  # no image → not training-grade
        for p in photos:
            download(p.url) → images/<sha256>.jpg
            write_label(weight=h.qty_lbs, item=c.name, date=h.date)
```

## Hand-off after extraction

Once Tracks A + B are done (and C if granted), update:

- `aperture/checkpoint.md` — add line under "Active workstream" noting
  Farmbrite historical extraction complete + path to dataset
- `aperture/training-loop/README.md` — replace "Sources #3 — gold
  standard" placeholder with actual row count + photo count
- `memory/project_aperture.md` — update with the dataset summary so
  future sessions know it exists

## Anti-patterns to avoid

- ❌ Don't manually transcribe weights from screenshots. CSV has them.
- ❌ Don't right-click-save photos one at a time. If we don't get API
  access, build a Playwright headless scraper using Ava's session
  cookie — but only after CSV is done so we know what records to target.
- ❌ Don't filter the CSV downloads by date in the UI. Pull
  "Download All Records," filter offline.
- ❌ Per `feedback_real_data_not_synthetic`: do not GPT-generate any
  fake records to "fill gaps." If a harvest has no photo, the row gets
  flagged `image_present: false` and excluded from training; that's fine.
