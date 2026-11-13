"""flask imagehub import-values, and the values in the pages, the API and the export.
Synthetic leaf discs; database. No value is ever printed by the command."""
import csv
import io
import zipfile

import pytest

from plugins.imagehub.tests import extra_leaf

FIELDS = ("source_zip", "source_member", "disc_area", "lesions")


@pytest.fixture
def world(app, tmp_path, monkeypatch):
    yield from extra_leaf.world(app, tmp_path, monkeypatch)


def _keys(world, owner="a_id"):
    return dict(world["sql"](
        "SELECT source_member, source_zip FROM _fd.imagehub_images WHERE owner_id = %s "
        "AND dataset = %s", world[owner], world["dataset_id"]))


def _write_csv(path, rows, header=FIELDS):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    return str(path)


def _b_image(world):
    """One image owned by user B in the same dataset."""
    world["sql"]("INSERT INTO _fd.imagehub_images (owner_id, dataset, match_status, fields, "
                 "source_zip, source_member, mime, original_name) VALUES (%s, %s, 'unmatched', "
                 "'{}'::jsonb, 'leaves.zip', 'Trial 2026/LEAF-0098_day01_top.png', 'image/png', "
                 "'LEAF-0098_day01_top.png')", world["b_id"], world["dataset_id"], commit=True)
    return ("leaves.zip", "Trial 2026/LEAF-0098_day01_top.png")


def _member(keys, name):
    return next(m for m in keys if m.endswith(name))


def _audits(world):
    return world["sql"]("SELECT after_state FROM _fd.plugin_audit WHERE actor = %s "
                        "AND resource = 'imagehub_images' AND action = 'import_values' "
                        "ORDER BY created_at", world["a_id"])


def _values(world, member):
    (fields,), = world["sql"]("SELECT fields FROM _fd.imagehub_images WHERE dataset = %s "
                              "AND source_member = %s", world["dataset_id"], member)
    return {k: fields.get(k) for k in ("disc_area", "lesions")}


@pytest.fixture
def loaded(world, tmp_path):
    world["load"]()
    keys = _keys(world)
    one = _member(keys, "LEAF-0001_day01_top.png")
    two = _member(keys, "LEAF-0002_day01_top.png")
    three = _member(keys, "LEAF-0003_day03_bottom.png")
    b_zip, b_member = _b_image(world)
    path = _write_csv(tmp_path / "values.csv", [
        ("leaves.zip", one, "12.345", "2"),
        ("leaves.zip", two, "3.5", ""),
        ("leaves.zip", three, "250.25", "0"),
        ("leaves.zip", "Trial 2026/LEAF-0077_day01_top.png", "1.0", "1"),   # not catalogued
        (b_zip, b_member, "99.0", "9"),                                     # B's image
    ])
    return {**world, "csv": path, "one": one, "two": two, "three": three, "b_member": b_member}


def _import(w, *extra):
    return w["invoke"]("import-values", "--dataset", w["dataset_id"], "--source", w["csv"], *extra)


def test_dry_run_counts_and_writes_nothing(loaded):
    no_as = _import(loaded)
    assert no_as.exit_code == 0 and "give --as" in no_as.output
    dry = _import(loaded, "--as", loaded["a_email"])
    assert dry.exit_code == 0, dry.output
    out = dry.output
    assert "csv rows usable=5" in out and "joined to your images=3" in out
    assert "not in your catalog=2 (of which another owner's image=1)" in out
    assert "disc_area: set=3 changed=0 removed=0 unchanged=0" in out
    assert "lesions: set=2 changed=0 removed=0 unchanged=1" in out
    assert "DRY RUN" in out
    for value in ("12.345", "250.25", "99.0", "3.5"):
        assert value not in out
    assert _values(loaded, loaded["one"]) == {"disc_area": None, "lesions": None}
    assert _audits(loaded) == []


def test_apply_needs_as_and_backup_done(loaded):
    assert "--apply needs --as" in _import(loaded, "--apply", "--backup-done").output
    refused = _import(loaded, "--apply", "--as", loaded["a_email"])
    assert refused.exit_code != 0 and "--backup-done" in refused.output
    assert _values(loaded, loaded["one"])["disc_area"] is None


def test_apply_writes_own_images_only_and_is_safe_to_rerun(loaded):
    args = ("--as", loaded["a_email"], "--apply", "--backup-done")
    applied = _import(loaded, *args)
    assert applied.exit_code == 0, applied.output
    assert "APPLIED: images written=3" in applied.output
    assert _values(loaded, loaded["one"]) == {"disc_area": 12.345, "lesions": 2}
    assert _values(loaded, loaded["two"]) == {"disc_area": 3.5, "lesions": None}
    assert _values(loaded, loaded["three"]) == {"disc_area": 250.25, "lesions": 0}
    assert _values(loaded, loaded["b_member"]) == {"disc_area": None, "lesions": None}
    # The parsed keys are untouched.
    (fields,), = loaded["sql"]("SELECT fields FROM _fd.imagehub_images WHERE source_member = %s",
                               loaded["one"])
    assert fields["sample_id"] == "LEAF-0001" and fields["side"] == "top" and fields["day"] == 1

    again = _import(loaded, *args)
    assert "images written=0" in again.output and "unchanged=3" in again.output
    audits = _audits(loaded)
    assert len(audits) == 2
    assert audits[0][0]["written"] == 3 and audits[1][0]["written"] == 0
    assert audits[0][0]["fields"] == ["disc_area", "lesions"]


def test_an_empty_cell_removes_the_key(loaded, tmp_path):
    _import(loaded, "--as", loaded["a_email"], "--apply", "--backup-done")
    loaded["csv"] = _write_csv(tmp_path / "clear.csv", [("leaves.zip", loaded["one"], "")],
                               header=("source_zip", "source_member", "disc_area"))
    result = _import(loaded, "--as", loaded["a_email"], "--apply", "--backup-done")
    assert "disc_area: set=0 changed=0 removed=1 unchanged=0" in result.output
    assert _values(loaded, loaded["one"]) == {"disc_area": None, "lesions": 2}


def test_a_csv_with_a_bad_row_is_not_applied(loaded, tmp_path):
    loaded["csv"] = _write_csv(tmp_path / "bad.csv", [
        ("leaves.zip", loaded["one"], "1.0", "1"),
        ("leaves.zip", loaded["two"], "a lot", "1"),
    ])
    result = _import(loaded, "--as", loaded["a_email"], "--apply", "--backup-done")
    assert result.exit_code != 0 and "line 3: disc_area is not a number" in result.output
    assert _values(loaded, loaded["one"])["disc_area"] is None


def test_values_show_filter_sort_and_export(loaded):
    _import(loaded, "--as", loaded["a_email"], "--apply", "--backup-done")
    client, dataset_id = loaded["client"], loaded["dataset_id"]

    def found(**args):
        response = client.get("/imagehub/api/images", query_string={"dataset": dataset_id, **args})
        assert response.status_code == 200
        return response.get_json()

    assert found(area_from="10")["total"] == 2
    assert found(area_from="10", area_to="100")["total"] == 1
    assert found(area_to="3.5")["total"] == 1
    # Sorted by disc_area first (ui.sort): smallest first, images without a value last.
    ordered = [i["image"].get("disc_area") for i in found()["images"]]
    assert ordered[:3] == [3.5, 12.345, 250.25] and ordered[3] is None

    page = client.get("/imagehub/ui", query_string={"dataset": dataset_id}).get_data(as_text=True)
    assert "12.3 mm2" in page and "250.2 mm2" in page and "12.345" not in page
    image_id = loaded["sql"]("SELECT id::text FROM _fd.imagehub_images WHERE source_member = %s",
                             loaded["one"])[0][0]
    detail = client.get(f"/imagehub/ui/images/{image_id}").get_data(as_text=True)
    assert "Disc area" in detail and "12.3 mm2" in detail

    # The export holds the stored value, not rounded.
    out = loaded["run"]("export", "--dataset", dataset_id, "--as", loaded["a_email"])
    archive = zipfile.ZipFile(out.strip().rsplit(": ", 1)[1])
    rows = list(csv.DictReader(io.StringIO(archive.read("metadata.csv").decode())))
    by_name = {r["original_name"]: r for r in rows}
    assert by_name["LEAF-0001_day01_top.png"]["disc_area"] == "12.345"
    assert by_name["LEAF-0003_day03_bottom.png"]["disc_area"] == "250.25"
    assert by_name["LEAF-0004_day01_top.png"]["disc_area"] == ""
