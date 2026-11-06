"""Two unlike datasets in one database: the spheroid example and invented leaf discs.

The leaf disc dataset has no wells, VIDs or annotations, one key column and its own
file names. Both go through the real commands, the API, the pages and an export;
neither ever shows the other's rows. Synthetic data only; every row is removed by
owner afterwards.
"""
import csv
import io
import re
import uuid
import zipfile

import pytest

from app import get_db
from config import supabase_extension
from plugins.imagehub import cli, config, export, ingest, routes as routes_module
from plugins.imagehub.tests import leaf, synthetic


@pytest.fixture
def both(app, tmp_path, monkeypatch):
    token = uuid.uuid4().hex[:10]
    disk = tmp_path / "disk"
    disk.mkdir()
    spheroid_book = synthetic.make_workbook(tmp_path / synthetic.names(token)["workbook"], token)
    synthetic.make_disk(str(disk), token)
    leaf_book = leaf.make_workbook(tmp_path / "leaves.xlsx")
    photos = leaf.make_disk(str(disk))

    for module in (ingest, routes_module, cli):
        monkeypatch.setattr(module, "DISK_ROOT", str(disk))
    monkeypatch.setattr(cli, "REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(export, "EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("IMAGEHUB_PUBLIC_STORAGE_URL", "http://kong:8000")
    spheroid, leaves = synthetic.dataset(token), leaf.dataset()
    monkeypatch.setattr(config, "datasets", lambda: {spheroid.id: spheroid, leaves.id: leaves})
    monkeypatch.setenv("IMAGEHUB_DATASET", spheroid.id)

    with app.app_context():
        email = f"imagehub-leaf-{token}@test.com"
        user_id = str(supabase_extension.client.auth.admin.create_user({
            "email": email, "password": uuid.uuid4().hex, "email_confirm": True,
        }).user.id)
        db = get_db()
        with db.cursor() as cur:
            cur.execute("INSERT INTO _fd.user_roles (user_id, role) VALUES (%s, 'admin') "
                        "ON CONFLICT (user_id) DO UPDATE SET role = 'admin'", (user_id,))
        db.commit()
    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = user_id

    yield {"app": app, "client": client, "email": email, "user_id": user_id, "token": token,
           "spheroid": spheroid, "leaf": leaves, "photos": photos,
           "books": {spheroid.id: str(spheroid_book), leaves.id: str(leaf_book)}}

    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT storage_path, preview_path FROM _fd.imagehub_images WHERE owner_id = %s", (user_id,))
            blobs = {p for row in cur.fetchall() for p in row if p}
            for table in ("exports", "annotations", "images", "wells", "legends"):
                cur.execute(f"DELETE FROM _fd.imagehub_{table} WHERE owner_id = %s", (user_id,))
            cur.execute("DELETE FROM _fd.plugin_audit WHERE actor = %s", (user_id,))
            cur.execute("DELETE FROM _fd.user_roles WHERE user_id = %s", (user_id,))
        db.commit()
        ingest.delete_blobs(*blobs)
        supabase_extension.client.auth.admin.delete_user(user_id)


def _invoke(both, *args):
    return both["app"].test_cli_runner().invoke(args=["imagehub", *args])


def _run(both, *args):
    result = _invoke(both, *args)
    assert result.exit_code == 0, f"{args}: {result.output}\n{result.exception!r}"
    return result.output


def _as(both):
    return ("--as", both["email"])


def _one(both, sql, *params):
    with both["app"].app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        db.rollback()
    return rows


def _load(both, ds):
    _run(both, "import-metadata", "--dataset", ds.id, "--source", both["books"][ds.id], "--apply", *_as(both))
    return _run(both, "catalog", "--dataset", ds.id, "--apply", *_as(both))


def _zip(output):
    return zipfile.ZipFile(output.strip().rsplit(": ", 1)[1])


def test_leaf_discs_and_spheroids_side_by_side(both):
    spheroid, leaves = both["spheroid"], both["leaf"]
    _load(both, spheroid)
    catalog = _load(both, leaves)
    assert "'matched': 16" in catalog and "'unmatched': 1" in catalog

    counts = dict(_one(both, "SELECT dataset, count(*) FROM _fd.imagehub_wells WHERE owner_id = %s "
                             "GROUP BY 1", both["user_id"]))
    assert counts[leaves.id] == 5 and counts[spheroid.id] > 0
    # A leaf disc has none of the spheroid columns; its own values are in fields.
    row = _one(both, "SELECT fields ? 'vid', fields ? 'well', fields, props FROM _fd.imagehub_wells WHERE owner_id = %s "
                     "AND dataset = %s AND fields ->> 'sample_id' = 'LEAF-0002'", both["user_id"], leaves.id)[0]
    assert row[0] is False and row[1] is False
    assert row[2]["species_norm"] == ["oak"] and row[2]["dose_unit"] == "g/m2"
    assert row[3]["Grower"] == leaf.GROWERS[0]
    # Images link within their own dataset only.
    linked = _one(both, "SELECT i.dataset, w.dataset FROM _fd.imagehub_images i "
                        "JOIN _fd.imagehub_wells w ON w.id = i.well_id WHERE i.owner_id = %s",
                  both["user_id"])
    assert linked and all(a == b for a, b in linked)

    # Upload selects by the leaf dataset's own fields; keys start with its id.
    out = _run(both, "upload", "--dataset", leaves.id, *_as(both), "--group", leaf.TRIAL,
               "--field", "side=top", "--field", "day=1")
    assert "'uploaded': 5" in out  # four discs and the photo that is not in the sheet
    paths = [p for (p,) in _one(both, "SELECT storage_path FROM _fd.imagehub_images WHERE owner_id = %s "
                                      "AND storage_path IS NOT NULL", both["user_id"])]
    assert len(paths) == 5 and all(p.startswith(f"imagehub-images/{leaves.id}/") for p in paths)
    assert "no annotation zip" in _invoke(both, "import-via", "--dataset", leaves.id, *_as(both),
                                          "--member", "x.json").output

    # The API and pages: one dataset at a time, by its own filters.
    client = both["client"]

    def found(**args):
        response = client.get("/imagehub/api/images", query_string=args)
        assert response.status_code == 200
        return response.get_json()

    oak = found(dataset=leaves.id, species="oak")
    assert oak["total"] == 8
    assert {i["sample"]["sample_id"] for i in oak["images"]} == {"LEAF-0001", "LEAF-0002"}
    assert found(dataset=leaves.id, side="bottom", from_day="2")["total"] == 4
    leaf_ids = {i["id"] for i in found(dataset=leaves.id)["images"]}
    spheroid_ids = {i["id"] for i in found()["images"]}  # the active dataset
    assert len(leaf_ids) == 17 and spheroid_ids and not leaf_ids & spheroid_ids
    # A spheroid filter means nothing to leaf discs, and the other way round.
    assert found(dataset=leaves.id, treatment="ibrutinib")["total"] == 17
    assert not {i["id"] for i in found(species="oak")["images"]} & leaf_ids

    page = client.get("/imagehub/ui", query_string={"dataset": leaves.id}).get_data(as_text=True)
    assert leaves.title in page and "Species" in page and "Treatment" not in page
    assert "LEAF-0001" in page and "SYNTH" not in page
    detail = client.get(f"/imagehub/ui/images/{oak['images'][0]['id']}").get_data(as_text=True)
    assert "Fertiliser" in detail and "Volgnummer" not in detail

    # Exports: each holds its own dataset only, with its own columns and dashboard.
    archive = _zip(_run(both, "export", "--dataset", leaves.id, *_as(both), "--species", "oak"))
    assert "this dataset's filters" in _invoke(both, "export", "--dataset", leaves.id, *_as(both),
                                               "--treatment", "x").output
    names = archive.namelist()
    images = [n for n in names if n.startswith("images/")]
    assert len(images) == 8 and all(n.endswith(".png") and "/LEAF-000" in n for n in images)
    assert not [n for n in names if n.startswith("annotations/")]
    rows = list(csv.DictReader(io.StringIO(archive.read("metadata.csv").decode())))
    assert {r["sample_id"] for r in rows} == {"LEAF-0001", "LEAF-0002"}
    assert set(rows[0]) >= {"trial", "species", "dose", "dose_unit", "Chlorophyll (SPAD)"}
    assert "vid" not in rows[0] and "Grower" not in rows[0]
    assert archive.read("README.txt").decode().startswith("Leaf disc export")
    html = archive.read("dashboard.html").decode()
    assert '"key": ["sample_id"]' in html and "Leaf disc dashboard" in html
    for name in names:
        content = archive.read(name)
        assert not re.search(rb"SYNTH|VID9|Grower", content), name

    spheroid_zip = _zip(_run(both, "export", "--dataset", spheroid.id, *_as(both), "--max-images", "50"))
    for name in spheroid_zip.namelist():
        assert b"LEAF-" not in spheroid_zip.read(name) and "LEAF-" not in name, name
