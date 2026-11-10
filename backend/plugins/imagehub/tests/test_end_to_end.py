"""The whole flow through the real CLI commands, on synthetic data only.

Reports and exports go to a temporary folder; every row and blob is removed by owner.
"""
import csv
import io
import json
import re
import uuid
import zipfile

import pytest

from app import get_db
from config import supabase_extension
from plugins.imagehub import cli, config, export, ingest, routes as routes_module
from plugins.imagehub.tests import synthetic


@pytest.fixture
def world(app, tmp_path, monkeypatch):
    token = uuid.uuid4().hex[:10]
    disk = tmp_path / "disk"
    disk.mkdir()
    n = synthetic.names(token)
    workbook = synthetic.make_workbook(tmp_path / n["workbook"], token)
    files = synthetic.make_disk(str(disk), token)

    monkeypatch.setattr(ingest, "DISK_ROOT", str(disk))
    monkeypatch.setattr(routes_module, "DISK_ROOT", str(disk))
    monkeypatch.setattr(cli, "DISK_ROOT", str(disk))
    monkeypatch.setattr(cli, "REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(export, "EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("IMAGEHUB_PUBLIC_STORAGE_URL", "http://kong:8000")
    # The CLI uses the active dataset: make it the example config fitted to this
    # token's synthetic disk.
    dataset = synthetic.dataset(token)
    monkeypatch.setattr(config, "datasets", lambda: {dataset.id: dataset})

    with app.app_context():
        email = f"imagehub-e2e-{token}@test.com"
        user = supabase_extension.client.auth.admin.create_user({
            "email": email, "password": uuid.uuid4().hex, "email_confirm": True,
        }).user
        user_id = str(user.id)
        db = get_db()
        with db.cursor() as cur:
            cur.execute("INSERT INTO _fd.user_roles (user_id, role) VALUES (%s, 'admin') "
                        "ON CONFLICT (user_id) DO UPDATE SET role = 'admin'", (user_id,))
        db.commit()

    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = user_id

    yield {
        "app": app, "client": client, "email": email, "user_id": user_id, "names": n,
        "workbook": str(workbook), "files": files, "tmp": tmp_path, "token": token,
    }

    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT storage_path, preview_path FROM _fd.imagehub_images WHERE owner_id = %s", (user_id,))
            blobs = [p for row in cur.fetchall() for p in row if p]
            cur.execute("SELECT source_storage_path FROM _fd.imagehub_annotations WHERE owner_id = %s", (user_id,))
            blobs += [row[0] for row in cur.fetchall() if row[0]]
            for table in ("exports", "annotations", "images", "wells", "legends"):
                cur.execute(f"DELETE FROM _fd.imagehub_{table} WHERE owner_id = %s", (user_id,))
            cur.execute("DELETE FROM _fd.plugin_audit WHERE actor = %s", (user_id,))
            cur.execute("DELETE FROM _fd.user_roles WHERE user_id = %s", (user_id,))
        db.commit()
        ingest.delete_blobs(*set(blobs))
        supabase_extension.client.auth.admin.delete_user(user_id)


def _run(world, *args):
    result = world["app"].test_cli_runner().invoke(args=["imagehub", *args])
    assert result.exit_code == 0, f"{args}: {result.output}\n{result.exception!r}"
    return result.output


def _one(world, sql, *params):
    with world["app"].app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        db.rollback()
    return rows


def _as(world):
    return ("--as", world["email"])


def _rows_of(world, table):
    return _one(world, f"SELECT count(*) FROM _fd.imagehub_{table} WHERE owner_id = %s", world["user_id"])[0][0]


def test_metadata_import_dry_run_apply_and_rerun(world):
    # A dry run writes nothing, and shows the mappings.
    output = _run(world, "import-metadata", "--source", world["workbook"])
    assert "DRY RUN" in output and "venetoclax + s-63845" in output
    assert _rows_of(world, "wells") == 0

    assert "'inserted': 6" in _run(world, "import-metadata", "--source", world["workbook"], "--apply", *_as(world))
    assert "'unchanged': 6" in _run(world, "import-metadata", "--source", world["workbook"], "--apply", *_as(world))
    assert _rows_of(world, "wells") == 6 and _rows_of(world, "legends") == 1

    # Every value the config reads is in fields, by the config's names.
    columns = ("fields ->> 'vid', fields -> 'vids', fields ->> 'well', fields ->> 'treatment_raw', "
               "fields -> 'treatment_norm', fields -> 'stimulation_norm', fields ->> 'concentration', "
               "fields ->> 'concentration_unit', props")
    rows = {r[2]: r for r in _one(world, f"SELECT {columns} FROM _fd.imagehub_wells WHERE owner_id = %s", world["user_id"])}
    assert "A4" not in rows  # a well without a VID is an empty plate position

    vid, vids, _, raw, norm, stim, concentration, unit, props = rows["A2"]
    assert vid == "99002;99003" and vids == ["99002", "99003"]
    assert raw == "ABT-199;S-63845" and norm == ["venetoclax", "s-63845"]
    assert stim == ["il-2/15/21/cpg", "acd3/acd28"]
    assert concentration == "1;2" and unit == "nM"
    assert props["Target"] == "JAK1/2/3, TYK2, ACVR1"

    assert rows["A1"][0] == "99001"  # a float in Excel, text here
    assert rows["A1"][8]["proliferation index (CLL)_2"] == 1.6
    assert rows["A3"][3] == "rituximab " and rows["A3"][4] == ["rituximab"]  # raw is kept
    assert rows["A3"][8]["Sex"].startswith("niet aanwezig")  # raw is kept
    assert rows["B1"][7] == "ng/mL" and rows["B1"][5] == ["acd3/acd29"]

    audit = _one(world, "SELECT action, after_state FROM _fd.plugin_audit WHERE actor = %s AND resource = 'imagehub_wells'", world["user_id"])
    assert len(audit) == 2 and audit[0][0] == "import"

    report = (world["tmp"] / "reports" / "metadata_report.csv").read_text().splitlines()
    assert any(line.endswith("skipped_no_vid") for line in report)
    assert any(line.endswith("skipped_blank") for line in report)
    assert (world["tmp"] / "reports" / "metadata_long.csv").exists()


def _catalog_ready(world):
    _run(world, "import-metadata", "--source", world["workbook"], "--apply", *_as(world))
    return _run(world, "catalog", "--apply", *_as(world))


def _status(world, name, source_zip=None):
    sql = ("SELECT match_status, fields ->> 'vid', experiment, fields ->> 'channel', fields ->> 'channel_norm', "
           "fields ->> 'variant', well_id, (fields ->> 'timepoint_minutes')::int "
           "FROM _fd.imagehub_images WHERE owner_id = %s AND original_name = %s")
    rows = _one(world, sql, world["user_id"], name)
    assert rows, name
    return rows[0]


def test_catalog_links_and_reports(world):
    output = _catalog_ready(world)
    assert "APPLIED" in output
    assert "'unchanged'" in _run(world, "catalog", "--apply", *_as(world))
    total = _rows_of(world, "images")
    assert "'inserted'" not in _run(world, "catalog", "--apply", *_as(world))
    assert _rows_of(world, "images") == total

    n = world["names"]
    hit = _status(world, "VID99001_A1_1_04d00h00m.jpg")
    assert hit[0] == "matched" and hit[2] == n["experiment_a"] and hit[3:5] == ("jpg", "jpg") and hit[7] == 5760

    # Several VIDs in one cell: both link to the same well.
    first, second = _status(world, "VID99002_A2_1_00d12h00m.jpg"), _status(world, "VID99003_A2_1_00d12h00m.jpg")
    assert first[0] == second[0] == "matched" and first[6] == second[6]

    # One VID in the experiment, no VID in the name: inferred, with the channel kept.
    phase = _status(world, "Phase_B1_1_00d00h00m.tif")
    assert phase[0] == "inferred" and phase[1] == "BD991" and phase[3:5] == ("Phase", "PC")
    assert _status(world, "Brightfield_B1_1_00d00h00m.tif")[3:5] == ("Brightfield", "BF")

    # Nested set: inferred through its zip, the annotation copy keeps its suffix.
    nested = _status(world, world["files"]["nested_image"])
    assert nested[0] == "inferred" and nested[2] == n["experiment_b"] and nested[3:5] == ("BF", "BF") and nested[5] == "1L"

    assert _status(world, "VID99001_H9_1_00d00h00m.jpg")[0] == "unmatched"
    assert _status(world, "PC_H9_1_00d00h00m.tif")[0:2] == ("unmatched", None)
    assert _status(world, "VID99009_A1_1_00d00h00m.jpg")[0] == "unmatched"

    reports = world["tmp"] / "reports"
    rows = list(csv.DictReader((reports / "catalog_report.csv").open()))
    reasons = {r["source_member"].rsplit("/", 1)[-1]: r["match_reason"] for r in rows}
    assert reasons["VID99009_A1_1_00d00h00m.jpg"] == "no_metadata_for_experiment"
    assert reasons["VID99001_H9_1_00d00h00m.jpg"] == "not_in_experiment"
    assert reasons["Phase_B1_1_00d00h00m.tif"] == "vid_inferred_from_experiment"
    assert "Snapshot.PNG" in (reports / "catalog_not_parsed.csv").read_text()
    assert "raw.zip" in (reports / "catalog_nested_not_opened.csv").read_text()
    without = (reports / "wells_without_images.csv").read_text()
    assert f"{n['workbook']},EXP-A,5," in without  # A5 has no image; A1 has
    assert f"{n['workbook']},EXP-A,2," not in without


def test_via_upload_view_export_and_delete(world):
    _catalog_ready(world)
    files, client, n = world["files"], world["client"], world["names"]

    def via(member):
        return _run(world, "import-via", *_as(world), "--member", member, "--upload-json")

    output = via(files["via_aa"])
    assert f"inserted | {files['annotated']}" in output
    assert "no_image_with_this_name | VID99999" in output  # reported, not fatal
    assert f"unchanged | {files['annotated']}" in via(files["via_aa"])
    assert "size_differs_from_image" in _run(world, "import-via", *_as(world), "--member", files["via_wrong_size"])
    via(files["via_unknown"])
    assert "inserted" in via(files["via_nested_aa"])
    assert "inserted" in via(files["via_nested_bb"])

    labels = dict(_one(world, "SELECT annotator_label, count(*) FROM _fd.imagehub_annotations WHERE owner_id = %s GROUP BY 1", world["user_id"]))
    assert labels == {"AA": 2, "unknown": 1, "BB": 1}
    # Both nested annotators on one image, though the BB zip has its own copy.
    assert _one(world, "SELECT count(DISTINCT image_id) FROM _fd.imagehub_annotations a JOIN _fd.imagehub_images i ON i.id = a.image_id WHERE a.owner_id = %s AND i.original_name = %s", world["user_id"], files["nested_image"])[0][0] == 1
    # The original files are in the bucket, unchanged.
    stored = _one(world, "SELECT count(*) FROM storage.objects WHERE bucket_id = %s AND name LIKE %s AND name LIKE %s", ingest.BUCKET, "spheroid_example/via/%", "%set_AA.json")
    assert stored[0][0] == 1

    # Selection only, skips on a re-run, TIFF gets a preview.
    assert "select at least one filter" in world["app"].test_cli_runner().invoke(args=["imagehub", "upload", *_as(world)]).output
    args = ("upload", *_as(world), "--experiment", n["experiment_a"], "--source-zip", "NK.zip")
    assert "'uploaded': 5" in _run(world, *args)  # the unmatched H9 image is in the folder too
    assert "'skipped': 5" in _run(world, *args)
    _run(world, "upload", *_as(world), "--annotated", "--source-zip", "Annotation.zip", "--experiment", n["experiment_a"])
    tiff_row = _one(world, "SELECT preview_path, id FROM _fd.imagehub_images WHERE owner_id = %s AND original_name = %s", world["user_id"], "VID99001_A1_1_01d00h00m.tif")[0]
    assert tiff_row[0].endswith(".preview.jpg")

    # Search page and API: filters, status, time, channel, regions.
    found = client.get("/imagehub/api/images", query_string={"experiment": n["experiment_a"], "from_day": "4", "to_day": "4"}).get_json()
    assert {i["original_name"] for i in found["images"]} == {files["annotated"]}
    assert all(i["image"]["timepoint_minutes"] == 4 * 1440 for i in found["images"])
    assert {i["status"] for i in found["images"]} == {"in bucket"}
    page = client.get("/imagehub/ui", query_string={"experiment": n["experiment_a"], "min_regions": "2", "annotated": "1"}).get_data(as_text=True)
    assert "AA 2, unknown 0" in page and "4d 0h 0m" in page
    assert client.get("/imagehub/api/images", query_string={"experiment": n["experiment_a"], "min_regions": "3"}).get_json()["total"] == 0
    assert client.get("/imagehub/api/images", query_string={"experiment": n["experiment_b"], "channel_norm": "PC"}).get_json()["total"] == 2

    # Detail page: the overlay and well metadata.
    image_id = _one(world, "SELECT id FROM _fd.imagehub_images WHERE owner_id = %s AND source_zip = 'Annotation.zip' AND original_name = %s", world["user_id"], files["annotated"])[0][0]
    detail = client.get(f"/imagehub/ui/images/{image_id}").get_data(as_text=True)
    assert "<ellipse" in detail and "<polygon" in detail and "AA: 2 regions" in detail and "unknown: 0 regions" in detail
    assert "4d 0h 0m" in detail and "Ibrutinib" in detail

    # Export through the CLI.
    output = _run(world, "export", *_as(world), "--experiment", n["experiment_a"], "--max-images", "20")
    assert "0 missing" in output
    archive_path = output.strip().rsplit(": ", 1)[1]
    archive = zipfile.ZipFile(archive_path)
    assert archive.testzip() is None
    file_names = archive.namelist()
    assert {"metadata.csv", "README.txt", "dashboard.html"} <= set(file_names)

    reader = csv.DictReader(io.StringIO(archive.read("metadata.csv").decode()))
    header, rows = reader.fieldnames, list(reader)
    assert header[:6] == ["image_file", "original_name", "experiment", "vid", "well", "field"]
    assert header[-1] == "volgnummer" and "well_note" in header
    assert header.index("treatment_raw") < header.index("Viability (%)") < header.index("Sample date")
    assert "Sex" not in header  # excluded by the example config
    row = next(r for r in rows if r["original_name"] == files["annotated"])
    assert row["regions_AA"] == "2" and row["regions_unknown"] == "0" and row["regions_total"] == "2"
    assert row["treatment_norm"] == "ibrutinib" and row["stimulation_norm"] == "IL-2/15/21/CpG"
    assert archive.read(row["image_file"]) == synthetic.jpeg()
    assert any(n.startswith("annotations/AA_") for n in file_names)

    readme = archive.read("README.txt").decode()
    assert "Viability (%): Percentage of live cells" in readme
    assert "Sample date: no description in the lab sheet" in readme and "Sex" not in readme

    html = archive.read("dashboard.html").decode()
    embedded = json.loads(html.split('id="embedded" type="application/json">')[1].split("</script>")[0])
    assert len(embedded["rows"]) == len(rows) and embedded["images"]
    assert embedded["annotations"][row["image_file"]][0]["label"] == "AA"
    assert {w["well"] for w in embedded["wells_without_images"]} >= {"A5"}
    # Wells without images carry the dashboard's key columns, from the sheet.
    key = embedded["layout"]["key"]
    assert key == ["experiment", "vid", "well"]
    assert all(set(w) == set(key) for w in embedded["wells_without_images"])
    assert embedded["name"] == "Spheroid imaging export"

    # Merged spelling, across two sheets of one workbook.
    other = _run(world, "export", *_as(world), "--experiment", n["experiment_b"], "--max-images", "20")
    merged = zipfile.ZipFile(other.strip().rsplit(": ", 1)[1])
    reader = csv.DictReader(io.StringIO(merged.read("metadata.csv").decode()))
    assert "Proliferation index (CLL)" not in reader.fieldnames and "Specific lysis (%)" in reader.fieldnames
    assert next(reader)["proliferation index (CLL)"] == "2.5"
    assert _rows_of(world, "exports") == 2

    # Every mutation left an audit row.
    actions = {(r[0], r[1]) for r in _one(world, "SELECT resource, action FROM _fd.plugin_audit WHERE actor = %s", world["user_id"])}
    assert {("imagehub_wells", "import"), ("imagehub_images", "catalog"), ("imagehub_images", "upload"),
            ("imagehub_annotations", "import"), ("imagehub_annotations", "upload_json"),
            ("imagehub_exports", "create")} <= actions

    # Deleting removes the rows and the blobs.
    json_paths = [r[0] for r in _one(world, "SELECT source_storage_path FROM _fd.imagehub_annotations WHERE image_id = %s", image_id)]
    assert len(json_paths) == 2 and all(json_paths)
    deleted = client.delete(f"/imagehub/api/images/{image_id}", json={})
    assert deleted.status_code == 200 and deleted.get_json()["blobs_removed"] is True
    assert client.get(f"/imagehub/ui/images/{image_id}").status_code == 404
    left = _one(world, "SELECT count(*) FROM _fd.imagehub_annotations WHERE image_id = %s", image_id)
    assert left[0][0] == 0
    assert not _one(world, "SELECT 1 FROM storage.objects WHERE bucket_id = %s AND name LIKE %s", ingest.BUCKET, f"%{image_id}%")
    # Its VIA files had only that image, so they are gone from the bucket as well.
    for path in json_paths:
        assert not _one(world, "SELECT 1 FROM storage.objects WHERE bucket_id = %s AND name = %s", *path.split("/", 1))


def _fails(world, *args):
    result = world["app"].test_cli_runner().invoke(args=["imagehub", *args])
    assert result.exit_code != 0, f"{args}: {result.output}"
    return result.output


def test_commands_take_the_dataset_and_its_own_filters(world):
    ds = synthetic.dataset(world["token"])
    n = world["names"]
    # --dataset on every command; an unknown id names itself.
    for command, *more in (("import-metadata",), ("propose-aliases",), ("catalog",), ("upload", *_as(world)),
                           ("import-via", *_as(world), "--member", "x"), ("export", *_as(world))):
        assert "no dataset 'nope'" in _fails(world, command, "--dataset", "nope", *more), command
    _run(world, "import-metadata", "--dataset", ds.id, "--source", world["workbook"], "--apply", *_as(world))
    _run(world, "catalog", "--dataset", ds.id, "--apply", *_as(world))

    # The export's options are the dataset's ui.filters, by query parameter.
    listed = _run(world, "export", "--dataset", ds.id, *_as(world), "--list-filters")
    assert "--from-day | " in listed and "--channel-norm | " in listed
    assert "this dataset's filters: --experiment" in _fails(world, "export", *_as(world), "--nope", "1")
    assert "needs a value" in _fails(world, "export", *_as(world), "--treatment")
    out = _run(world, "export", "--dataset", ds.id, *_as(world), "--experiment", n["experiment_a"],
               "--from-day=1", "--to-day", "1", "--max-images", "20")
    archive = zipfile.ZipFile(out.strip().rsplit(": ", 1)[1])
    days = {r["day"] for r in csv.DictReader(io.StringIO(archive.read("metadata.csv").decode()))}
    assert days == {"1.0"}

    # Upload selects by image fields from the file name; whole numbers are compared as numbers.
    assert "DONE: {}" in _run(world, "upload", *_as(world), "--field", "well=ZZ9")
    assert "image field" in _fails(world, "upload", *_as(world), "--field", "nope=1")
    assert "whole number" in _fails(world, "upload", *_as(world), "--field", "timepoint_minutes=x")


def test_excluded_columns_appear_nowhere_in_the_zip(world):
    # The example config excludes Age and Sex; the synthetic sheets have both, with
    # a value of several words that would otherwise move to well_note.
    assert {"age", "sex"} <= config.excluded_names(synthetic.dataset(world["token"]).export)
    _catalog_ready(world)
    stored = _one(world, "SELECT count(*) FROM _fd.imagehub_wells WHERE owner_id = %s "
                         "AND (props ? 'Sex' OR props ? ' age')", world["user_id"])[0][0]
    assert stored > 0  # the database keeps them; only the export leaves them out
    out = _run(world, "export", *_as(world), "--max-images", "50")
    archive = zipfile.ZipFile(out.strip().rsplit(": ", 1)[1])
    names = archive.namelist()
    assert "dashboard.html" in names and "metadata.csv" in names and "README.txt" in names
    rows = list(csv.DictReader(io.StringIO(archive.read("metadata.csv").decode())))
    experiments = {r["experiment"] for r in rows}
    assert {world["names"]["experiment_a"], world["names"]["experiment_b"]} <= experiments
    forbidden = re.compile(rb"(?i)\b(age|sex|male|female)\b|about 70 at sampling|niet aanwezig")
    for name in names:
        hit = forbidden.search(archive.read(name))
        assert not hit, f"{name} holds {hit.group(0)!r}"
