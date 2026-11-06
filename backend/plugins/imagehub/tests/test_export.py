"""Export against the live stack. Synthetic data only."""
import copy
import csv
import io
import json
import os
import re
import zipfile

import pytest

from plugins.imagehub import export as export_module
from plugins.imagehub import config
from plugins.imagehub.rules import apply_steps
from plugins.imagehub.export import (
    _is_note, _metadata_csv, _readme, _sheet_group, _unique_path, column_value,
)
from plugins.imagehub.helpers import NO_DESCRIPTION, legend_descriptions

from .test_image_flow import ZIP_NAME, _tiff, stack  # noqa: F401 (fixture)


EXAMPLE = config.load_file(os.path.join(config.DATASET_DIRS[0], "spheroid_example.yaml"))
MERGES = EXAMPLE.export["sheet_columns"]["merge"]
COLUMNS = {c["name"]: c for s in EXAMPLE.export["sections"] for c in s.get("columns", ())}


@pytest.fixture
def export_dir(tmp_path, monkeypatch):
    path = tmp_path / "exports"
    monkeypatch.setattr(export_module, "EXPORT_DIR", str(path))
    return path


def _create(client, **filters):
    # The channel keeps real images out of every selection in these tests.
    return client.post("/imagehub/api/export", json={"filter": {"channel": "synthetic", **filters}})


def _zip(client, body):
    response = client.get(body["download_url"])
    assert response.status_code == 200
    return zipfile.ZipFile(io.BytesIO(response.data))


def test_export_from_disk_then_delete(stack, export_dir):
    client = stack["client"]
    response = _create(client, min_regions="0", from_day="0", to_day="1")
    assert response.status_code == 201, response.data
    body = response.get_json()
    assert body["n_files"] == 1 and body["n_missing"] == 0

    archive = _zip(client, body)
    names = archive.namelist()
    assert "metadata.csv" in names and "README.txt" in names and "MISSING.txt" not in names
    assert "dashboard.html" in names and body["dashboard_note"] is None

    rows = list(csv.DictReader(io.StringIO(archive.read("metadata.csv").decode())))
    assert len(rows) == 1
    row = rows[0]
    assert row["source_zip"] == ZIP_NAME
    assert row["file_status"] == "included"
    assert row["timepoint_minutes"] == "60" and row["day"] == "0.0417"
    assert row["regions_test"] == "1" and row["regions_total"] == "1"
    assert archive.read(row["image_file"]) == _tiff()

    via_name = next(n for n in names if n.startswith("annotations/test_"))
    via = json.loads(archive.read(via_name))
    entry = next(iter(via.values()))
    assert entry["filename"] == row["original_name"] and len(entry["regions"]) == 1

    readme = archive.read("README.txt").decode()
    assert "timepoint_minutes" in readme and '"from_day": "0"' in readme

    assert _audit_count(stack, "create") == 1
    deleted = client.delete(f"/imagehub/api/exports/{body['id']}", json={})
    assert deleted.status_code == 200
    assert not os.path.exists(export_dir / f"{body['id']}.zip")
    assert client.get(body["download_url"]).status_code == 404
    assert _audit_count(stack, "delete") == 1


def _audit_count(stack, action):
    from plugins.imagehub.tests.test_image_flow import _audit
    return _audit(stack["app"], stack["user_id"], action)


def test_export_prefers_bucket_and_lists_missing(stack, export_dir, monkeypatch, tmp_path):
    client, image_id = stack["client"], stack["image_id"]
    client.post("/imagehub/api/upload", json={"image_ids": [image_id]})

    # Disk gone: the uploaded image still exports, from the bucket.
    monkeypatch.setattr(export_module.ingest, "DISK_ROOT", str(tmp_path / "gone"))
    body = _create(client, min_regions="1", in_bucket="1", from_day="0", to_day="0.05").get_json()
    assert body["n_missing"] == 0
    rows = list(csv.DictReader(io.StringIO(_zip(client, body).read("metadata.csv").decode())))
    assert [(r["source_zip"], r["file_status"]) for r in rows] == [(ZIP_NAME, "included")]
    client.delete(f"/imagehub/api/exports/{body['id']}", json={})

    # Blob removed as well: listed as missing, and the export still succeeds.
    from plugins.imagehub.ingest import delete_blobs
    image = client.get(f"/imagehub/api/images/{image_id}").get_json()
    with stack["app"].app_context():
        delete_blobs(image["storage_path"], image["preview_path"])
    response = _create(client, min_regions="1", in_bucket="1", from_day="0", to_day="0.05")
    assert response.status_code == 201
    body = response.get_json()
    assert [m["reason"] for m in body["missing"]] == ["disk not connected"]
    archive = _zip(client, body)
    assert "MISSING.txt" in archive.namelist()
    client.delete(f"/imagehub/api/exports/{body['id']}", json={})


def test_export_refuses_empty_and_too_large(stack, export_dir, monkeypatch):
    client = stack["client"]
    empty = _create(client, experiment="no such experiment")
    assert empty.status_code == 400 and "no images" in empty.get_json()["error"]
    monkeypatch.setattr("plugins.imagehub.routes.MAX_IMAGES_REQUEST", 0)
    big = _create(client, min_regions="0", from_day="0", to_day="1")
    assert big.status_code == 400 and "over the limit" in big.get_json()["error"]


@pytest.mark.parametrize("role,status", [("curator", 201), ("accessor", 403), ("visualizer", 403)])
def test_export_rbac(stack, export_dir, role, status):
    stack["set_role"](role)
    response = _create(stack["client"], min_regions="0", from_day="0", to_day="0.05")
    assert response.status_code == status
    if status == 201:
        stack["client"].delete(f"/imagehub/api/exports/{response.get_json()['id']}", json={})


_SAMPLE = {"treatment_raw", "stimulation_norm", "concentration", "concentration_unit", "volgnummer"}


def _image(**values):
    """An export row: sample values go to the sample row, the rest to the row."""
    sample = {"stimulation_norm": [], "concentration_unit": "nM",
              **{k: v for k, v in values.items() if k in _SAMPLE}}
    return {"id": "a", "image": {"timepoint_minutes": 60}, "sample": sample, "props": {},
            **{k: v for k, v in values.items() if k not in _SAMPLE}}


def test_metadata_layout_notes_dates_and_regions():
    props = {
        "Origin": "niet aanwezig in CLL export bestand (ziekte)",
        "Sample date": "2023-01-05T00:00:00",
        "Viability (%)": 80.5,
        "gMFI CD25 (CLL)": 1,
        "Target": "JAK1/2/3, TYK2, ACVR1",
        "IGHV": "mutated",
        "%CD3+ (biobank)": 5,
    }
    images = [
        _image(props=props, treatment_raw="ABT-199;S-63845", concentration="1;2",
               stimulation_norm=["il-2/15/21/cpg", "acd3/acd29"], volgnummer="7"),
        _image(id="b", props={"Origin": "biopsy"}, treatment_raw="Ibrutinib"),
    ]
    text, groups, region_columns = _metadata_csv(
        images, {"a": "included", "b": "included"}, {"a": "images/a.jpg"},
        {"a": {"AA": 0, "unknown": 3}}, EXAMPLE,
    )
    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames
    first, second = list(reader)

    # Groups in the agreed order.
    assert header[:6] == ["image_file", "original_name", "experiment", "vid", "well", "field"]
    assert header[6:15] == [
        "timepoint_minutes", "day", "channel", "channel_norm", "variant", "match_status",
        "regions_AA", "regions_unknown", "regions_total",
    ]
    assert header[15] == "treatment_raw" and header[21] == "tissue"
    assert header[22:25] == ["gMFI CD25 (CLL)", "Target", "Viability (%)"]
    assert header[-8:] == [
        "well_note", "file_status", "source_zip", "source_member", "source_workbook",
        "source_sheet", "source_row", "volgnummer",
    ]
    assert header.index("Origin") > header.index("Viability (%)")
    assert header.index("%CD3+ (biobank)") > header.index("Viability (%)")

    # 0 regions differs from not annotated; the total is a sum.
    assert (first["regions_AA"], first["regions_unknown"], first["regions_total"]) == ("0", "3", "3")
    assert (second["regions_AA"], second["regions_total"]) == ("", "")

    # The note leaves its column, word for word, and normal values stay.
    assert first["Origin"] == ""
    assert first["Target"] == "JAK1/2/3, TYK2, ACVR1"
    assert first["well_note"] == "Origin: niet aanwezig in CLL export bestand (ziekte)"
    assert second["Origin"] == "biopsy" and second["well_note"] == ""

    assert first["Sample date"] == "2023-01-05"
    assert first["treatment_norm"] == "venetoclax;S-63845"
    assert first["stimulation_norm"] == "IL-2/15/21/CpG;aCD3/aCD29"
    assert second["treatment_norm"] == "ibrutinib"
    assert first["concentration_unit"] == "nM" and second["concentration_unit"] == ""
    assert region_columns == ["regions_AA", "regions_unknown"]
    assert list(groups["Patient and clinical"]) == ["%CD3+ (biobank)", "IGHV", "Origin", "Sample date"]


def test_merges_share_a_column_but_never_within_a_sheet():
    assert MERGES["Specific Lysis (%)"] == "Specific lysis (%)"
    images = [
        _image(id="a", source_workbook="W", source_sheet="A", props={"Specific Lysis (%)": 1, "Notch1": "WT"}),
        _image(id="b", source_workbook="W", source_sheet="B", props={"Specific lysis (%)": 2, "NOTCH1": "wild type"}),
        # One sheet with both spellings: two measurements, so they stay apart.
        _image(id="c", source_workbook="W", source_sheet="C", props={"Proliferation index (CD4)": 3, "proliferation index (CD4)": 4}),
    ]
    text, _, _ = _metadata_csv(
        images, {"a": "included", "b": "included", "c": "included"}, {}, {}, EXAMPLE,
    )
    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames
    a, b, c = list(reader)
    assert header.count("Specific lysis (%)") == 1 and "Specific Lysis (%)" not in header
    assert (a["Specific lysis (%)"], b["Specific lysis (%)"]) == ("1", "2")
    assert (a["NOTCH1"], b["NOTCH1"]) == ("WT", "wild type")
    assert c["Proliferation index (CD4)"] == "3" and c["proliferation index (CD4)"] == "4"


def test_every_merge_differs_only_in_spelling():
    from plugins.imagehub.helpers import legend_key
    assert all(legend_key(a) == legend_key(b) for a, b in MERGES.items())


def test_readme_uses_legend_or_says_there_is_none():
    groups = {
        "Flow and well results": {"%CD4+": "%CD4+", "Proliferation index (CLL)_2": "Proliferation index (CLL)_2"},
        "Patient and clinical": {"Origin": "Origin"},
    }
    descriptions = legend_descriptions([
        ["%CD4+", "Percentage of CD4 T cells"],
        ["proliferation index (CLL)", "Degree of proliferation"],
        ["Origin", '"'],
    ])
    readme = _readme({}, [], 0, [], groups, ["regions_AA"], descriptions, EXAMPLE)
    assert "  %CD4+: Percentage of CD4 T cells" in readme
    assert "  Proliferation index (CLL)_2: Degree of proliferation" in readme
    assert f"  Origin: {NO_DESCRIPTION}" in readme
    assert readme.index("Flow and well results") < readme.index("Patient and clinical")
    assert "  regions_AA: Number of regions from annotator AA" in readme


def test_unique_path():
    used = set()
    assert _unique_path("a/b.jpg", used) == "a/b.jpg"
    assert _unique_path("a/b.jpg", used) == "a/b_2.jpg"
    assert _unique_path("a/b.jpg", used) == "a/b_3.jpg"


@pytest.mark.parametrize("header,group", [
    ("%CD25high (CLL)", "results"), ("% Dividing cells (CD4)", "results"),
    ("gMFI Bcl-2 (CLL)", "results"), ("Viability (%)", "results"),
    ("Specific Lysis (%)", "results"), ("proliferation index (CLL)_2", "results"),
    ("E:T ratio", "results"), ("Time point T cells added to culture (hours)", "results"),
    ("Target", "results"), ("%CD5+CD19+", "results"),
    ("%CD5+CD19+ (biobank)", "clinical"), ("CD3-CD56+% (biobank)", "clinical"),
    ("Origin", "clinical"), ("%Lymphocytes", "clinical"), ("del17p13", "clinical"),
    ("HLA typering A2", "clinical"), ("T donor  ", "clinical"), ("Treatment status", "clinical"),
])
def test_sheet_groups_of_the_example(header, group):
    titles = {"results": "Flow and well results", "clinical": "Patient and clinical"}
    assert _sheet_group(EXAMPLE.export["sheet_columns"], header) == titles[group]


@pytest.mark.parametrize("raw,expected", [
    ("Ibrutinib", ["ibrutinib"]), ("ibrutinib", ["ibrutinib"]), ("rituximab ", ["rituximab"]),
    ("IgG", ["IgG"]), ("MALTi", ["MALTi"]), ("S-63845", ["S-63845"]),
    ("CONFIDENTIAL", ["CONFIDENTIAL"]), ("Bay", ["Bay"]), ("Bay 11-7082", ["Bay 11-7082"]),
    ("ABT-199;A-1331852", ["venetoclax", "A-1331852"]), ("Venetoclax", ["venetoclax"]),
    ("Blinatumomab;Lenalidomide", ["blinatumomab", "lenalidomide"]),
    (None, []),
])
def test_treatment_for_reading(raw, expected):
    row = {"image": {}, "sample": {"treatment_raw": raw}}
    assert column_value(COLUMNS["treatment_norm"], row) == ";".join(expected)


@pytest.mark.parametrize("raw", [
    "Ibrutinib", "rituximab ", "IgG", "CONFIDENTIAL", "Bay", "ABT-199;S-63845", "U0126",
])
def test_treatment_for_reading_has_the_same_content_as_the_normalised_value(raw):
    steps = EXAMPLE.metadata["derived"]["treatment_norm"]["steps"]
    row = {"image": {}, "sample": {"treatment_raw": raw}}
    readable = column_value(COLUMNS["treatment_norm"], row)
    assert [t.lower() for t in readable.split(";")] == apply_steps(raw, steps)


@pytest.mark.parametrize("token,expected", [
    ("il-2/15/21/cpg", "IL-2/15/21/CpG"), ("acd3/acd28", "aCD3/aCD28"),
    ("acd3/acd39", "aCD3/aCD39"), ("3t40 overnight", "3T40 overnight"),
    ("unstimulated", "unstimulated"),
])
def test_stimulation_for_reading(token, expected):
    row = {"image": {}, "sample": {"stimulation_norm": [token]}}
    assert column_value(COLUMNS["stimulation_norm"], row) == expected


@pytest.mark.parametrize("header,value,expected", [
    ("Origin", "niet aanwezig in CLL export bestand (Waldenstrom macroglobulinemia)", True),
    ("Target", "JAK1/2/3, TYK2, ACVR1", False),
    ("delTP53", "wild type", False), ("T donor volgnummer", "buffy 95", False),
    ("T donor age", "NA", False), ("Time point", "0h", False),
    ("Origin", "male", False), ("Age", 5, False), ("Age", None, False),
])
def test_notes_of_the_example(header, value, expected):
    assert _is_note(EXAMPLE.export["notes"], header, value) is expected


def test_day_and_unit_columns():
    day, unit = COLUMNS["day"], COLUMNS["concentration_unit"]
    assert column_value(day, {"image": {"timepoint_minutes": 5048}, "sample": {}}) == 3.5056
    assert column_value(day, {"image": {}, "sample": {}}) == ""
    assert column_value(unit, {"image": {}, "sample": {"concentration_unit": "nM"}}) == ""
    assert column_value(unit, {"image": {}, "sample": {"concentration": "1", "concentration_unit": "nM"}}) == "nM"


def test_a_dataset_without_sheet_columns_or_notes_exports_only_its_columns():
    raw = config.load_file(os.path.join(config.DATASET_DIRS[0], "spheroid_example.yaml")).raw
    raw = {**{k: v for k, v in raw.items() if k != "dashboard"}, "export": {"sections": [
        {"title": "Leaf", "columns": [{"name": "plot", "from": "sample.tissue", "description": "Plot"},
                                      {"name": "file_status", "description": "Status"}]},
        {"annotations": "Regions"},
    ]}}
    leaf = config.Dataset(raw, "leaf.yaml")
    images = [_image(props={"Origin": "a b c d"})]
    images[0]["sample"] = {"tissue": "north"}
    text, groups, _ = _metadata_csv(images, {"a": "included"}, {}, {"a": {"AA": 2}}, leaf)
    assert text.splitlines() == ["plot,file_status,regions_AA,regions_total", "north,included,2,2"]
    assert groups == {}
    readme = _readme({}, images, 1, [], groups, ["regions_AA"], {}, leaf)
    # Without export.name the title is the dataset's; no sheet or note sections.
    assert readme.splitlines()[0] == f"{leaf.title} export"
    assert "Sheet-specific" not in readme and "well_note" not in readme



def test_excluded_columns_leave_csv_readme_and_dashboard_layout():
    # Names are compared without case and outer spaces; a configured column can go too.
    raw = copy.deepcopy(EXAMPLE.raw)
    raw["export"]["exclude"] = ["sex", " Age ", "tissue", "Viability (%)"]
    raw["ui"]["filters"] = [f for f in raw["ui"]["filters"] if f["field"] != "sample.tissue"]
    raw["dashboard"]["expected"].remove("tissue")
    ds = config.Dataset(raw, "exclude.yaml")
    images = [_image(props={"Sex": "male", "age ": "about 70 at sampling", "Viability (%)": 80, "IGHV": "M"})]
    images[0]["sample"]["tissue"] = "PB"
    text, groups, _ = _metadata_csv(images, {"a": "included"}, {}, {}, ds)
    header = text.splitlines()[0].split(",")
    assert "IGHV" in header
    assert not {"Sex", "age ", "tissue", "Viability (%)"} & set(header)
    # Not as a note either: a sentence in an excluded column stays out of well_note.
    assert "male" not in text and "about 70" not in text and ",PB," not in text
    readme = _readme({}, images, 1, [], groups, [], {"sex": "Self-reported sex"}, ds)
    assert not re.search(r"(?i)\b(sex|age|tissue|viability)\b", readme)
    assert "Viability (%)" not in export_module.dashboard_layout(ds)["values"]


def _refused(raw, part):
    with pytest.raises(config.ConfigError, match=re.escape(part)):
        config.Dataset(raw, "exclude.yaml")


def test_exclude_refuses_what_would_still_show_the_column():
    raw = copy.deepcopy(EXAMPLE.raw)
    # A filter on it would put its value in the export's filter line.
    raw["export"]["exclude"] = ["tissue"]
    _refused(raw, "'tissue' is also filtered on by ui.filters[3]")
    raw["ui"]["filters"] = [f for f in raw["ui"]["filters"] if f["field"] != "sample.tissue"]
    # The dashboard may not be built around it.
    _refused(raw, "dashboard.expected[5]: column 'tissue' is in export.exclude")
    raw["dashboard"]["expected"].remove("tissue")
    config.Dataset(raw, "exclude.yaml")
    raw["dashboard"]["group"] = "tissue"
    _refused(raw, "dashboard.group: column 'tissue' is in export.exclude")
