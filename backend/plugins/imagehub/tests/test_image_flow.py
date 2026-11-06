"""Routes, RBAC, preview and delete against the live stack. Synthetic data only."""
import io
import json
import uuid
import zipfile

import pytest
import requests
from flask import g
from PIL import Image

from app import get_db
from config import supabase_extension
from plugins.imagehub import ingest, routes as routes_module

ZIP_NAME = "synthetic-spheroid-test.zip"
MEMBER = "Fam/Exp/VID1_A1_1_00d01h00m.tif"
VIA_MEMBER = "Fam/Exp/via_AA.json"
REGIONS = '[{"shape_attributes": {"name": "ellipse"}, "region_attributes": {}}]'


def _tiff():
    out = io.BytesIO()
    Image.new("L", (32, 24), 128).save(out, "TIFF")
    return out.getvalue()


@pytest.fixture
def stack(app, tmp_path, monkeypatch):
    with zipfile.ZipFile(tmp_path / ZIP_NAME, "w") as zf:
        zf.writestr(MEMBER, _tiff())
        zf.writestr(VIA_MEMBER, json.dumps({
            "x": {"filename": MEMBER.rsplit("/", 1)[-1], "regions": json.loads(REGIONS)},
        }))
    monkeypatch.setattr(ingest, "DISK_ROOT", str(tmp_path))
    monkeypatch.setattr(routes_module, "DISK_ROOT", str(tmp_path))
    # Inside this container the browser-side host is the gateway's service name.
    monkeypatch.setenv("IMAGEHUB_PUBLIC_STORAGE_URL", "http://kong:8000")

    with app.app_context():
        user = supabase_extension.client.auth.admin.create_user({
            "email": f"imagehub-{uuid.uuid4().hex[:10]}@test.com",
            "password": uuid.uuid4().hex,
            "email_confirm": True,
        }).user
        user_id = str(user.id)
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO _fd.user_roles (user_id, role) VALUES (%s, 'admin') "
                "ON CONFLICT (user_id) DO UPDATE SET role = 'admin'", (user_id,),
            )
            cur.execute(
                "INSERT INTO _fd.imagehub_images (owner_id, dataset, match_status, "
                "fields, source_zip, source_member, mime, original_name) "
                "VALUES (%s, 'spheroid_example', 'unmatched', "
                "'{\"vid\": \"1\", \"well\": \"A1\", \"timepoint_minutes\": 60, "
                "\"channel\": \"synthetic\"}', %s, %s, 'image/tiff', %s) RETURNING id",
                (user_id, ZIP_NAME, MEMBER, MEMBER.rsplit("/", 1)[-1]),
            )
            image_id = str(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO _fd.imagehub_annotations (owner_id, image_id, annotator_label, "
                "regions, source_file) VALUES (%s, %s, 'test', %s::jsonb, 'test') RETURNING id",
                (user_id, image_id, REGIONS),
            )
            annotation_id = str(cur.fetchone()[0])
        db.commit()

    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = user_id
        session["email"] = user.email

    def set_role(role):
        with app.app_context():
            db = get_db()
            with db.cursor() as cur:
                cur.execute("UPDATE _fd.user_roles SET role = %s WHERE user_id = %s", (role, user_id))
            db.commit()

    yield {"client": client, "image_id": image_id, "annotation_id": annotation_id,
           "user_id": user_id, "set_role": set_role, "app": app}

    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "SELECT storage_path, preview_path FROM _fd.imagehub_images WHERE source_zip = %s",
                (ZIP_NAME,),
            )
            leftovers = [p for row in cur.fetchall() for p in row if p]
            cur.execute("DELETE FROM _fd.imagehub_images WHERE source_zip = %s", (ZIP_NAME,))
            cur.execute("DELETE FROM _fd.imagehub_exports WHERE owner_id = %s", (user_id,))
            cur.execute("DELETE FROM _fd.plugin_audit WHERE actor = %s", (user_id,))
            cur.execute("DELETE FROM _fd.user_roles WHERE user_id = %s", (user_id,))
        db.commit()
        ingest.delete_blobs(*leftovers)
        supabase_extension.client.auth.admin.delete_user(user_id)


def _import_via(stack, member=VIA_MEMBER):
    app = stack["app"]
    with app.test_request_context("/"):
        app.preprocess_request()
        with g.db.cursor() as cur:
            report = ingest.import_via(cur, ZIP_NAME, member, stack["user_id"])
            path = ingest.upload_via_json(cur, ZIP_NAME, member)
        g.db.commit()
    return report, path


def _object_exists(app, storage_path):
    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM storage.objects WHERE bucket_id = %s AND name = %s",
                storage_path.split("/", 1),
            )
            count = cur.fetchone()[0]
        db.rollback()
    return count == 1


def test_via_json_goes_to_the_bucket_and_leaves_with_its_last_annotation(stack):
    report, path = _import_via(stack)
    assert report == [(MEMBER.rsplit("/", 1)[-1], "inserted")]
    assert path.startswith("imagehub-images/spheroid_example/via/") and path.endswith("_via_AA.json")
    assert _object_exists(stack["app"], path)

    client, image_id = stack["client"], stack["image_id"]
    annotations = client.get(f"/imagehub/api/images/{image_id}").get_json()["annotations"]
    aa = next(a for a in annotations if a["annotator_label"] == "AA")
    assert len(aa["regions"]) == 1
    assert client.delete(f"/imagehub/api/annotations/{aa['id']}", json={}).status_code == 200
    assert not _object_exists(stack["app"], path)


def test_deleting_an_image_removes_its_json_too(stack):
    _, path = _import_via(stack)
    response = stack["client"].delete(f"/imagehub/api/images/{stack['image_id']}", json={})
    assert response.status_code == 200
    assert not _object_exists(stack["app"], path)


def _bucket_objects(app, image_id):
    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "SELECT name FROM storage.objects WHERE bucket_id = %s AND name LIKE %s",
                (ingest.BUCKET, f"%{image_id}%"),
            )
            names = [r[0] for r in cur.fetchall()]
        db.rollback()
    return names


def _audit(app, user_id, action):
    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM _fd.plugin_audit WHERE actor = %s AND action = %s",
                (user_id, action),
            )
            count = cur.fetchone()[0]
        db.rollback()
    return count


def test_upload_view_delete(stack):
    client, image_id = stack["client"], stack["image_id"]

    response = client.post("/imagehub/api/upload", json={"image_ids": [image_id]})
    assert response.status_code == 200, response.data
    assert response.get_json() == [{"id": image_id, "status": "uploaded"}]
    assert _audit(stack["app"], stack["user_id"], "upload") == 1
    assert len(_bucket_objects(stack["app"], image_id)) == 2  # TIFF + preview

    again = client.post("/imagehub/api/upload", json={"image_ids": [image_id]})
    assert again.get_json()[0]["status"] == "skipped"

    image = client.get(f"/imagehub/api/images/{image_id}").get_json()
    assert image["preview_path"] and image["annotations"][0]["annotator_label"] == "test"
    original = requests.get(image["url"], timeout=20)
    assert original.status_code == 200 and original.content == _tiff()
    preview = requests.get(image["display_url"], timeout=20)
    assert preview.status_code == 200
    assert Image.open(io.BytesIO(preview.content)).size == (32, 24)

    deleted = client.delete(f"/imagehub/api/images/{image_id}", json={})
    assert deleted.status_code == 200 and deleted.get_json()["blobs_removed"] is True
    assert _bucket_objects(stack["app"], image_id) == []
    assert client.get(f"/imagehub/api/images/{image_id}").status_code == 404
    assert _audit(stack["app"], stack["user_id"], "delete") == 1


def test_delete_annotation_keeps_image(stack):
    client = stack["client"]
    response = client.delete(f"/imagehub/api/annotations/{stack['annotation_id']}", json={})
    assert response.status_code == 200
    image = client.get(f"/imagehub/api/images/{stack['image_id']}").get_json()
    assert image["annotations"] == []


@pytest.mark.parametrize("role,read,write", [
    ("admin", 200, 200),
    ("curator", 200, 200),
    ("accessor", 200, 403),
    ("visualizer", 403, 403),
])
def test_rbac(stack, role, read, write):
    stack["set_role"](role)
    client, image_id = stack["client"], stack["image_id"]
    assert client.get("/imagehub/ui").status_code == read
    assert client.get(f"/imagehub/ui/images/{image_id}").status_code == read
    assert client.get("/imagehub/api/images?vid=1").status_code == read
    assert client.get(f"/imagehub/api/images/{image_id}").status_code == read
    assert client.post("/imagehub/api/upload", json={"image_ids": [image_id]}).status_code == write


def test_upload_reports_disconnected_disk(stack, monkeypatch, tmp_path):
    monkeypatch.setattr(routes_module, "DISK_ROOT", str(tmp_path / "gone"))
    response = stack["client"].post("/imagehub/api/upload", json={"image_ids": [stack["image_id"]]})
    assert response.get_json()[0]["status"] == "disk not connected"


def test_query_page_filters_and_escapes(stack):
    client = stack["client"]
    page = client.get(f"/imagehub/ui?in_bucket=1&concentration=<script>x").get_data(as_text=True)
    assert "<script>x" not in page
    found = client.get("/imagehub/api/images?annotated=1&from_day=0&to_day=1").get_json()
    assert stack["image_id"] in [i["id"] for i in found["images"]]
    assert found["images"][0]["status"]
    nothing = client.get("/imagehub/api/images?annotated=1&from_day=99").get_json()
    assert stack["image_id"] not in [i["id"] for i in nothing["images"]]


def test_detail_page_draws_regions(stack):
    client, image_id = stack["client"], stack["image_id"]
    client.post("/imagehub/api/upload", json={"image_ids": [image_id]})
    page = client.get(f"/imagehub/ui/images/{image_id}").get_data(as_text=True)
    assert 'id="imagehub-overlay"' in page and "test: 0 regions" in page
    assert "(1 could not be drawn)" in page  # the fixture's ellipse has no coordinates
