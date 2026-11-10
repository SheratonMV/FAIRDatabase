"""Two datasets in one database, on synthetic data only: their rows never mix.

Both datasets read the same workbook and disk, so every source name is shared.
Every row is removed by owner afterwards.
"""
import json
import uuid

import pytest
from flask import g

from app import get_db
from config import supabase_extension
from plugins.imagehub import config, ingest
from plugins.imagehub.tests import synthetic

@pytest.fixture
def two(app, tmp_path):
    token = uuid.uuid4().hex[:10]
    disk = tmp_path / "disk"
    disk.mkdir()
    workbook = synthetic.make_workbook(tmp_path / synthetic.names(token)["workbook"], token)
    synthetic.make_disk(str(disk), token)
    first = synthetic.dataset(token)
    raw = synthetic.example_raw()
    raw["id"] = "spheroid_example_copy"
    second = synthetic.dataset(token, base=raw)

    with app.app_context():
        user = supabase_extension.client.auth.admin.create_user({
            "email": f"imagehub-ds-{token}@test.com",
            "password": uuid.uuid4().hex,
            "email_confirm": True,
        }).user
    user_id = str(user.id)
    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("INSERT INTO _fd.user_roles (user_id, role) VALUES (%s, 'accessor') "
                        "ON CONFLICT (user_id) DO UPDATE SET role = 'accessor'", (user_id,))
        db.commit()

    yield {"app": app, "user_id": user_id, "workbook": str(workbook), "disk": str(disk),
           "datasets": (first, second)}

    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT storage_path, preview_path FROM _fd.imagehub_images WHERE owner_id = %s",
                        (user_id,))
            blobs = {p for row in cur.fetchall() for p in row if p}
            for table in ("images", "wells", "legends"):
                cur.execute(f"DELETE FROM _fd.imagehub_{table} WHERE owner_id = %s", (user_id,))
            cur.execute("DELETE FROM _fd.plugin_audit WHERE actor = %s", (user_id,))
            cur.execute("DELETE FROM _fd.user_roles WHERE user_id = %s", (user_id,))
        db.commit()
        ingest.delete_blobs(*blobs)
        supabase_extension.client.auth.admin.delete_user(user_id)


def _import(two, ds):
    """Import the workbook and catalog the disk as dataset ``ds``."""
    app = two["app"]
    with app.test_request_context("/"):
        app.preprocess_request()
        with g.db.cursor() as cur:
            data = ingest.read_metadata(two["workbook"], dataset=ds)
            _, well_counts = ingest.write_wells(cur, data, two["user_id"])
            walked = ingest.walk_images(two["disk"], dataset=ds)
            index = ingest.load_match_index(cur, dataset=ds)
            images = [ingest.match_image(i, index, dataset=ds) for i in walked["images"]]
            _, image_counts = ingest.write_images(cur, images, two["user_id"])
        g.db.commit()
    return data, images, well_counts, image_counts


def _rows(two, sql):
    with two["app"].app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(sql, (two["user_id"],))
            rows = cur.fetchall()
        db.rollback()
    return rows


def test_same_sources_in_two_datasets_stay_apart(two):
    first, second = two["datasets"]
    data, images, wells, catalogued = _import(two, first)
    assert wells["inserted"] == len(data["wells"]) > 0
    assert catalogued["inserted"] == len(images) > 0

    # The same workbook and zips again, as another dataset: new rows, none overwritten.
    _, _, wells_2, catalogued_2 = _import(two, second)
    assert wells_2["inserted"] == wells["inserted"]
    assert catalogued_2["inserted"] == catalogued["inserted"]
    for table in ("wells", "images", "legends"):
        counts = dict(_rows(two, f"SELECT dataset, count(*) FROM _fd.imagehub_{table} "
                                 "WHERE owner_id = %s GROUP BY dataset"))
        assert set(counts) == {first.id, second.id}, table
        assert counts[first.id] == counts[second.id], table

    # A re-run of one dataset changes nothing.
    _, _, again, catalogued_again = _import(two, first)
    assert again["inserted"] == again["updated"] == 0
    assert catalogued_again["inserted"] == catalogued_again["updated"] == 0

    # ``fields`` holds what the config read, by the config's names.
    stored = {
        (row[0], row[1]): row[2] for row in _rows(
            two, "SELECT source_sheet, source_row, fields FROM _fd.imagehub_wells "
                 "WHERE owner_id = %s AND dataset = 'spheroid_example'")
    }
    for well in data["wells"]:
        assert stored[(well["source_sheet"], well["source_row"])] == json.loads(json.dumps(well["fields"]))


def _object_count(two, storage_path):
    with two["app"].app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT count(*) FROM storage.objects WHERE bucket_id = %s AND name = %s",
                        storage_path.split("/", 1))
            count = cur.fetchone()[0]
        db.rollback()
    return count


def test_each_dataset_uploads_under_its_own_key(two):
    first, second = two["datasets"]
    _import(two, first)
    _import(two, second)
    app, paths = two["app"], {}
    with app.test_request_context("/"):
        app.preprocess_request()
        with g.db.cursor() as cur:
            # The same file of the same zip, once per dataset.
            cur.execute("SELECT source_zip, source_member FROM _fd.imagehub_images "
                        "WHERE owner_id = %s AND dataset = %s AND mime = 'image/jpeg' "
                        "ORDER BY source_member LIMIT 1", (two["user_id"], first.id))
            source = cur.fetchone()
            for ds in (first, second):
                cur.execute("SELECT id FROM _fd.imagehub_images WHERE dataset = %s "
                            "AND source_zip = %s AND source_member = %s", (ds.id, *source))
                (image,) = ingest.select_images(cur, image_ids=[str(cur.fetchone()[0])], dataset=ds.id)
                assert ingest.upload_image(cur, image, disk_root=two["disk"]) == "uploaded"
                cur.execute("SELECT storage_path FROM _fd.imagehub_images WHERE id = %s", (image["id"],))
                paths[ds.id] = cur.fetchone()[0]
        g.db.commit()
    for ds in (first, second):
        assert paths[ds.id].startswith(f"imagehub-images/{ds.id}/")
        assert _object_count(two, paths[ds.id]) == 1
    # Deleting one dataset's copy leaves the other's.
    with app.app_context():
        assert ingest.delete_blobs(paths[first.id])
    assert _object_count(two, paths[first.id]) == 0
    assert _object_count(two, paths[second.id]) == 1


def test_pages_and_api_show_one_dataset_at_a_time(two, monkeypatch):
    first, second = two["datasets"]
    monkeypatch.setattr(config, "datasets", lambda: {first.id: first, second.id: second})
    monkeypatch.setenv("IMAGEHUB_DATASET", first.id)
    _import(two, first)
    _import(two, second)
    client = two["app"].test_client()
    with client.session_transaction() as session:
        session["user"] = two["user_id"]
    count = dict(_rows(two, "SELECT dataset, count(*) FROM _fd.imagehub_images "
                            "WHERE owner_id = %s GROUP BY dataset"))

    def found(**args):
        return client.get("/imagehub/api/images", query_string=args).get_json()

    assert found()["total"] >= count[first.id]
    copy = found(dataset=second.id)
    ids = {r[0] for r in _rows(two, "SELECT id::text, dataset FROM _fd.imagehub_images "
                                    "WHERE owner_id = %s") if r[1] == second.id}
    assert {i["id"] for i in copy["images"]} <= ids
    assert client.get("/imagehub/api/images?dataset=nope").status_code == 404

    # A sample list field and an image field filter by containment.
    treated = found(dataset=second.id, treatment="venetoclax")
    assert treated["total"] > 0
    assert all("venetoclax" in i["sample"]["treatment_norm"] for i in treated["images"])
    assert found(dataset=second.id, treatment="venetoclax", channel_norm="none")["total"] == 0

    page = client.get("/imagehub/ui", query_string={"dataset": second.id}).get_data(as_text=True)
    assert second.title in page and 'name="dataset"' in page
    image_id = copy["images"][0]["id"]
    detail = client.get(f"/imagehub/ui/images/{image_id}").get_data(as_text=True)
    assert f"dataset={second.id}" in detail

