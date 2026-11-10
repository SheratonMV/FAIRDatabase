# Image hub plugin

Links image files to the sample rows of lab spreadsheets, stores a selection of the
images and their VIA annotations in a Supabase bucket, and makes everything queryable.
A selection can be exported as one zip with a dashboard, for people without database
access.

The plugin started with spheroid imaging, but nothing in the code depends on spheroid
columns: each dataset is described by one config file (see [Datasets](#datasets)).

- **Sample rows** (every row of every sheet) and the **image catalog** (every image in
  the zips) are complete in the database.
- **The bucket** holds only a selection, uploaded on request.
- **The images stay in zips** on a disk and are read from there when needed. Nothing is
  unzipped.

Real data (images, workbooks, VIA json, reports, and the config of a real dataset) never
goes in git. Tests use `tests/synthetic.py`.

## Datasets

A dataset is one YAML file in `datasets/`. The shipped `datasets/spheroid_example.yaml`
describes a spheroid experiment with invented names, and is the reference for every key;
it is marked `example: true`. Configs of real datasets go in `datasets/local/`, which is
git-ignored: their experiment names, lab codes and annotator initials are real.

The active dataset is `IMAGEHUB_DATASET`, or else the one config that is not an example.
The pages take `?dataset=<id>`. Every row in the database carries its dataset id, so
several datasets live side by side; one dataset's pages and exports never show another's.

A config is checked when it is loaded: an unknown key, a wrong type, a regex that does
not compile or a field that does not exist stops the app with the file and key named.

| Section | Says |
|---|---|
| `metadata` | Which sheet headers become which fields (`header`, or `header_regex` with a unit), which fields a row needs, the columns of `metadata_long.csv` (`long_report`), and `derived` fields made with steps: `split`, `strip`, `lower`, `upper`, `synonyms`, `synonyms_any_case`, `split_off_prefix`, `replace`, `lower_capitalised`, `drop_empty`, `dedupe`. All other columns are kept in `props` under their own header |
| `images` | Which zips to read, at which folder level the experiment is, which copies to skip, and how a file name becomes fields (one regex with named groups, then per field: groups, a sum, a copy, upper case, synonyms, whole numbers) |
| `images.match` | Which image field must equal which sample field (`keys`; a list field matches on any of its values), which sample field a folder names (`group_field`), aliases, and groups where a missing key takes the group's only value (`infer_single`) |
| `annotations` | VIA files: the annotator's label from the file name, and labels for nested zips |
| `ui` | The query page: filters (select, exact text, or a range with a scale), sort order, result columns, and the rows of the image page |
| `export` | The export zip: the columns of `metadata.csv` in sections, each with a description for `README.txt`, the sheet column groups, header merges, free-text notes, and `exclude`: columns that never go in an export |
| `dashboard` | The dashboard in the export, by `metadata.csv` column: which columns name a sample row and its label, the group, time and channel columns, units, the thumbnail caption, expected columns, default groups and values, the annotator shown first, and tab names |

In `ui` and `export` a field is named `group` (the image's experiment, or its folder),
`image.<field>` (from the file name) or `sample.<field>` (from the sheet).

### Adding a dataset

1. Copy `datasets/spheroid_example.yaml` to `datasets/local/<id>.yaml`, set `id`,
   `title` and remove `example: true`.
2. Fill in `metadata` (with `source`, the sheets on the disk) and `images` for your sheets and file names. Dry runs show what
   would be read without writing anything: `import-metadata` lists the fields found per
   sheet, `catalog` lists how the images would link.
3. Fill in `ui`, `export` and `dashboard` with your own fields.
4. Restart the app. Commands take `--dataset <id>`; without it they use the active
   dataset.

## Start the server

The plugin runs in the FAIRDatabase stack (`backend/docker-compose.yml`). The disk with
the zips is mounted read-only in the Flask container, at `/mnt/d` unless
`IMAGEHUB_DISK_ROOT` says otherwise; a local `docker-compose.override.yml` can add that
mount, which is not in git. Without the disk the app still works: images in the bucket
stay available, the others show "disk not connected".

### Environment variables

The Flask container only gets the variables listed for it in the compose files, so set
these under `flask-app: environment:` in your `docker-compose.override.yml`, then
`docker compose up -d flask-app`. The plugin reads them through `kernel.env.get`.

| Variable | Default | What it does |
|---|---|---|
| `IMAGEHUB_DISK_ROOT` | `/mnt/d` | Folder inside the container where the disk with the zips is mounted. Must match the mount's target. |
| `IMAGEHUB_DATASET` | the one config that is not an example | Active dataset, used when a command or page has no `--dataset` / `?dataset=`. |
| `IMAGEHUB_PUBLIC_STORAGE_URL` | `http://localhost:8000` | Where the browser reaches the storage gateway, for image URLs. |
| `SUPABASE_KEY` | set by `docker-compose.yml` | Anon key, added to browser image URLs; the gateway wants an API key on storage. |

`flask run` does not reload code. After changing a Python file or a config, run
`docker compose restart flask-app`.

## Commands

All run inside the container. In the examples, `$SP` stands for
`docker exec fairdatabase-flask flask imagehub`, and `--as` is an admin or curator
email. Every step can be repeated: a re-run adds no duplicates. Every command takes
`--dataset <id>`, and otherwise works on the active dataset.

### 1. Import sample rows

Reads the workbooks (xlsx, csv, a folder or a zip) into `imagehub_wells`: `--source`,
or else the config's `metadata.source` on the disk. Without `--apply` nothing is
written, and it prints every derived value that the steps change.

```bash
$SP import-metadata
$SP import-metadata --apply --as you@example.org
```

Rows without a required field are skipped and reported. The raw value is always kept
next to the derived one.

### 2. Catalog the images

Lists the zips, without extracting, and links images to sample rows. Same `--apply`
rule.

```bash
$SP catalog
$SP catalog --apply --as you@example.org
```

To compare image folders with experiment names: `$SP propose-aliases`.

### 3. Import annotations

The annotator comes from the file name, by `annotations.annotator_pattern`.

```bash
$SP import-via --as you@example.org --member "Annotation/<folder>/set_AA.json" --upload-json
```

`--upload-json` also puts the original file in the bucket. Inside a nested zip, write
the path as `<zip>!/<member>`. Entries that cannot be linked are listed, not fatal.

### 4. Upload a selection

Needs at least one filter: `--name`, `--group` (or `--experiment`), `--field NAME=VALUE`
for an image field from the file name (repeat it for more), `--source-zip` or
`--annotated`. Already uploaded files are skipped. TIFF files also get a JPEG
preview, because browsers cannot show TIFF. Bucket keys start with the dataset id:
`<dataset>/<experiment>/<image id>_<file name>`.

```bash
$SP upload --as you@example.org --annotated --source-zip Annotation.zip
$SP upload --as you@example.org --group "<name>" --field vid=1169 --field well=A2 --limit 50
```

### 5. Export

```bash
$SP export --as you@example.org --list-filters
$SP export --as you@example.org --experiment "<name>" --treatment ibrutinib --from-day 2 --to-day 4
```

Besides `--min-regions`, `--annotated` and `--in-bucket`, the options are the dataset's
`ui.filters`, by query parameter (`from_day` is `--from-day`); `--list-filters` shows them.

The **Export** button on the search page does the same for the current filters, up to
500 images. Zips stay in `backend/uploads/imagehub-exports/` until deleted with
`DELETE /imagehub/api/exports/<id>`; there is no delete button yet.

### Reports

`backend/uploads/imagehub-reports/`, overwritten by each run:

| File | Content |
|---|---|
| `metadata_report.csv` | Status per sheet row, including skipped rows |
| `metadata_long.csv` | Everything imported, one value per line |
| `catalog_report.csv` | Status and match reason per image |
| `wells_without_images.csv` | Sample rows that no image links to |
| `catalog_not_parsed.csv` | Images with another name form, such as screenshots |
| `catalog_nested_not_opened.csv` | Nested archives that were not opened |

## Query

### Pages

`/imagehub/ui` has the filters and columns of the dataset's `ui` section, plus minimum
regions (one annotator must reach it), annotated only and in bucket. Click an image for
its annotations and sample row. Thumbnails show only for images in the bucket.
`/imagehub/api/images` takes the same filters and returns JSON, with the image and
sample fields of each image.

### SQL

Query the tables in Supabase Studio or with `psql` in the database container; example
queries are in `imagehub_queries.md`. Both connect with full rights, so the web routes'
ownership rules do not apply there.

Versions before this one had a read-only role, `imagehub_ro`, and
`python -m plugins.imagehub.query`. `sql/002_drop_query_role.sql` removes that role with
its grants and policies at the next start; no data is touched. An
`IMAGEHUB_RO_PASSWORD` left in `backend/.env` is no longer read and can be removed.

### Tables

| Table | Holds |
|---|---|
| `_fd.imagehub_wells` | One row per sample row: `dataset`, its source position, `fields` (the config's fields) and `props` (all other sheet columns under their own header) |
| `_fd.imagehub_images` | One row per image file: `dataset`, `fields` (from the file name), `experiment`, `well_id`, `match_status`, `source_zip`, `source_member`, `storage_path` |
| `_fd.imagehub_annotations` | `image_id`, `annotator_label`, `regions`, `source_file`, `source_storage_path` |
| `_fd.imagehub_legends` | Legend sheets, as documentation |
| `_fd.imagehub_exports` | Who exported what, and what was missing |

**Legacy columns.** `imagehub_wells` and `imagehub_images` still have the typed columns
of the first dataset: `vid`, `vids`, `well`, `volgnummer`, `treatment_raw`,
`treatment_norm`, `concentration`, `concentration_unit`, `tissue`, `stimulation`,
`stimulation_norm` on wells; `vid`, `well`, `field`, `timepoint_minutes`, `channel`,
`channel_norm`, `variant` on images (`imagehub_images.experiment` is not legacy: it is
the image's group). No code reads or writes them: rows imported before `fields` existed
keep their old values there, newer rows leave them empty. Read `fields` instead.

They are kept on purpose: the migrations run at every start and never drop a column or
a table. They can be removed later, in a separate migration, after a backup of the
database; that migration must also take them out of `sql/001_schema.sql` (which
creates and indexes them) and `sql/003_dataset.sql` (which copies them into `fields`),
or those files fail at the next start.

## The export zip

| File | Content |
|---|---|
| `images/` | The original files, unchanged, per experiment. From the bucket if present, else from the disk |
| `annotations/` | VIA json per annotator, only for the selected images. File names start with the label, or `unknown` |
| `metadata.csv` | One row per image, with the fields of its sample row |
| `README.txt` | Every column, with its description from the config or the Legend sheet |
| `dashboard.html` | Charts and thumbnails. Opens by double-click, works offline |
| `MISSING.txt` | Only if files could not be read: which ones, and why |

`metadata.csv` follows `export.sections`. The database keeps the raw values; only in
the csv, per the config: values can be rewritten by steps (for example the lab's own
spelling), a column can be empty without another (`only_if`), headers that differ only
in spelling share a column unless both occur in one sheet (`merge`), and text of several
words in a value column moves to `well_note` (`notes`). Midnight dates are shortened to
`YYYY-MM-DD`.

Check what you share: `metadata.csv` contains every sheet column, including coded
patient numbers, genetics, blood counts and treatment history, unless the config lists
it in `export.exclude`. An excluded column (a sheet header or a configured column,
compared without case) is left out of `metadata.csv`, `README.txt` and the dashboard,
also as a note in `well_note`; the database keeps it. The config refuses an excluded
column that the dashboard is built around or that a filter uses, since the filter line
would show its value.

## Dashboard

One file with no external requests; a Content-Security-Policy blocks them. A dashboard
in an export has its data, thumbnails (about 256 px) and annotation shapes embedded. If
the file would pass 20 MB, the thumbnails are left out and the export says so. **Open
file** also takes a `metadata.csv` or Excel file in that layout, without thumbnails.

| Tab | Shows |
|---|---|
| Overview | Counts per group, expected columns, missing values per column |
| Images | Thumbnails per sample row with a time slider and annotation layers |
| Time series | A region count over time, per condition |
| Values per group | Any numeric column per group, one dot per sample row with the median |
| Image vs values | Any two numeric columns, one dot per sample row. Click a dot for its images |
| Annotation status | Annotated images and regions per group and annotator |

Which columns the page treats specially comes from the config's `dashboard` section,
which the export puts in the page; the example config also renames two tabs to "Flow
endpoints" and "Image vs flow". A file opened by hand keeps the layout of the dashboard
it is opened in; on a page without one, every row is its own sample.

`regions_total` adds annotators together, so a region marked by two annotators counts
twice. Prefer one annotator's column. SheetJS is in `dashboard_assets/xlsx.full.min.js`.

## Roles

| Role | Can |
|---|---|
| admin | Everything |
| curator | Read everything; upload; export; delete what they own |
| accessor | Read everything |
| visualizer | Nothing: pages answer 403, though the sidebar link still shows |

There are no per-user grants or privacy roles: pseudonymisation happens before the data
arrive. Every mutation writes one row to `_fd.plugin_audit`; imports write one per run,
with counts.

## Links between images and sample rows

| `match_status` | Meaning |
|---|---|
| `matched` | The image's match keys (within its experiment, if the config has a `group_field`) found one sample row |
| `inferred` | A key was missing from the file name; the experiment has one value for it and is listed in `infer_single` |
| `unmatched` | No sample row found; the reason is in `catalog_report.csv` |
| `ambiguous` | Several sample rows fit, none picked |

## Tests

```bash
docker exec fairdatabase-flask pytest plugins/imagehub/tests -q
node plugins/imagehub/tests/dashboard_smoke.js    # on the host: the app image has no node
```

The database tests write synthetic rows under a temporary user and remove them
afterwards; run them on a separate test stack, not on a database with real data.
`test_golden.py` compares the whole pipeline on synthetic data with snapshots in
`tests/golden/`, so a change in output is always visible. `tests/leaf_discs.yaml` is a
second, invented dataset with nothing in common with spheroids (no wells, VIDs or
annotations; one key column); `test_leaf_db.py` runs it next to the spheroid example
in one database and checks that pages, filters, uploads and exports never mix them. `test_end_to_end.py` runs the
whole flow through the real commands. `dashboard_smoke.js` renders every tab without a
browser, so charts still need a look by eye.

## Layout

```
plugin.py             manifest: tables, bucket, roles, sidebar entry
config.py             loads and checks the dataset configs
rules.py              runs a config: value steps, file name parsing
routes.py             pages and API
cli.py                flask imagehub <command>
ingest.py             sample rows, catalog, upload, VIA import
export.py             the export zip
dashboard.py          builds dashboard.html from dashboard_assets/
helpers.py            pure functions: parsing, filters, display
datasets/             dataset configs; datasets/local/ is git-ignored
sql/                  idempotent migrations, applied at boot
templates/imagehub/   search page and detail page
imagehub_queries.md   example SQL
tests/                pytest and the dashboard smoke test
```

## Third-party code

The offline dashboard uses SheetJS 0.20.3 (Apache License 2.0), and nothing else in the plugin does. `dashboard_assets/xlsx.full.min.js` is the unmodified official build from https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js. Its licence is in `dashboard_assets/LICENSE-SheetJS.txt`.

## Credits

The imagehub plugin was written by Bénine Brouwer (University of Amsterdam / Amsterdam UMC) as a plugin for FAIRDatabase. If you use it in a publication, please cite this repository and the FAIRDatabase paper (Dorst et al., Front. Cell. Infect. Microbiol., 2024, doi:10.3389/fcimb.2024.1384809).
