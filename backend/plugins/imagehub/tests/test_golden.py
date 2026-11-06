"""Golden snapshot of the pure pipeline, on synthetic data only. No database.

Sheet reading, image walking, matching, metadata.csv, README.txt and the dashboard
data are compared with the files in ``golden/``. They end in ``.golden``
because the plugin's .gitignore keeps every csv and json out of git. Refactors must keep them equal.
After an intended change, rewrite them with::

    IMAGEHUB_UPDATE_GOLDEN=1 pytest plugins/imagehub/tests/test_golden.py

and review the diff before committing.
"""
import csv
import json
import os

import pytest

from plugins.imagehub import dashboard, export, ingest
from plugins.imagehub.helpers import annotator_label, legend_descriptions, parse_via
from plugins.imagehub.tests import synthetic

GOLDEN = os.path.join(os.path.dirname(__file__), "golden")
TOKEN = "GOLD"


class FakeCursor:
    """Answers the few SELECTs the pure code sends, by statement prefix."""

    def __init__(self, answers):
        self.answers = answers
        self.rows = []

    def execute(self, statement, params=None):
        for prefix, rows in self.answers.items():
            if statement.startswith(prefix):
                self.rows = rows
                return
        raise AssertionError(f"unexpected query: {statement}")

    def fetchall(self):
        return self.rows


def _jsonable(value):
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _annotations(ds, disk, files, images_by_name):
    """Annotation rows as the database would hold them, from the synthetic VIA files."""
    rows = []
    for key in ("via_aa", "via_unknown"):
        member = files[key]
        data = json.loads(ingest.read_member("Annotation.zip", member, disk))
        for entry in parse_via(data):
            image = images_by_name.get(entry["filename"])
            if image:
                rows.append((image["id"], annotator_label(member, ds.annotator_re),
                             f"Annotation.zip!/{member}", entry["regions"]))
    return sorted(rows, key=lambda r: (r[1], r[2]))


def run_pipeline(tmp_path, monkeypatch, ds=None):
    """``ds`` defaults to the example config fitted to the synthetic data."""
    ds = ds or synthetic.dataset(TOKEN)
    n = synthetic.names(TOKEN)
    disk = tmp_path / "disk"
    disk.mkdir()
    workbook = synthetic.make_workbook(tmp_path / n["workbook"], TOKEN)
    files = synthetic.make_disk(str(disk), TOKEN)

    data = ingest.read_metadata(str(workbook), dataset=ds)
    for number, well in enumerate(data["wells"], start=1):
        well["id"] = f"w{number}"
    wells_by_id = {w["id"]: w for w in data["wells"]}

    walked = ingest.walk_images(str(disk), dataset=ds)
    index = ingest.load_match_index(FakeCursor({
        "SELECT id, fields": [(w["id"], w["fields"]) for w in data["wells"]],
    }), dataset=ds)
    matched = [ingest.match_image(image, index, dataset=ds) for image in walked["images"]]
    for number, image in enumerate(matched, start=1):
        image["id"] = f"i{number}"

    # Rows as select_export_images returns them: image columns, then well columns.
    selected = []
    for image in sorted(matched, key=lambda i: (
        i["experiment"] or "", i["vid"] or "", i["well"] or "",
        i["timepoint_minutes"] if i["timepoint_minutes"] is not None else -1, i["source_member"],
    )):
        well = wells_by_id.get(image["well_id"], {})
        row = {c: image.get(c) for c in export._IMAGE_COLUMNS}
        row["storage_path"] = None
        selected.append(export.export_row(row, well))

    by_name = {i["original_name"]: i for i in selected}
    cur = FakeCursor({"SELECT image_id, annotator_label": _annotations(ds, str(disk), files, by_name)})
    via_files, counts, shapes = export._via_files(cur, selected)
    statuses = {i["id"]: "included" for i in selected}
    paths = {i["id"]: f"images/x/{i['original_name']}" for i in selected}
    metadata, groups, region_columns = export._metadata_csv(selected, statuses, paths, counts, ds)

    descriptions = {}
    for legend in data["legends"]:
        for key, text in legend_descriptions(legend["rows"]).items():
            descriptions.setdefault(key, text)
    readme = export._readme({"channel": "golden"}, selected, len(paths), [],
                            groups, region_columns, descriptions, ds)
    # The creation time is the only line that changes between runs.
    readme = "\n".join(l for l in readme.split("\n") if not l.startswith("Created: "))

    captured = {}
    monkeypatch.setattr(dashboard, "_render", lambda payload: captured.setdefault("p", payload) and "")
    dashboard.build_dashboard(
        metadata, {}, {paths[i]: v for i, v in shapes.items()}, [],
        {"created": "fixed", "filter": "{}", "name": "Spheroid export"},
        export.dashboard_layout(ds),
    )

    report_dir = tmp_path / "reports"
    ingest.write_reports(str(report_dir), data, {}, dataset=ds)
    with open(report_dir / "metadata_long.csv", encoding="utf-8") as fh:
        long_rows = list(csv.reader(fh))

    # Keys added after the snapshot was taken; tested on their own.
    later = ("dataset", "fields")
    state = {
        "wells": [{k: v for k, v in w.items() if k not in later} for w in data["wells"]],
        "sheets": data["sheets"],
        "report": data["report"],
        "legends": data["legends"],
        "walked": {k: v for k, v in walked.items() if k != "images"},
        "matched": [{k: v for k, v in i.items() if k != "id" and k not in later} for i in matched],
        "via_files": via_files,
        "metadata_long": long_rows,
        "dashboard": {k: v for k, v in captured["p"].items() if k != "layout"},
    }
    return {
        "state.json": json.dumps(_jsonable(state), indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        "metadata.csv": metadata,
        "README.txt": readme,
    }


def test_pipeline_matches_golden(tmp_path, monkeypatch):
    outputs = run_pipeline(tmp_path, monkeypatch)
    if os.getenv("IMAGEHUB_UPDATE_GOLDEN"):
        os.makedirs(GOLDEN, exist_ok=True)
        for name, text in outputs.items():
            with open(os.path.join(GOLDEN, name + ".golden"), "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        pytest.skip("golden files rewritten")
    for name, text in outputs.items():
        with open(os.path.join(GOLDEN, name + ".golden"), encoding="utf-8", newline="") as fh:
            assert text == fh.read(), f"{name} differs from golden"
