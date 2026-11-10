"""Ownership on the web routes: a user sees, uploads and exports only their own
images; an admin sees all of them. Synthetic rows only, removed by owner."""
import io
import uuid
import zipfile

import pytest

from app import get_db
from config import supabase_extension
from plugins.imagehub import export, ingest, routes as routes_module

DATASET = "spheroid_example"


def _new_user(app, role):
    with app.app_context():
        user = supabase_extension.client.auth.admin.create_user({
            "email": f"imagehub-own-{uuid.uuid4().hex[:10]}@test.com",
            "password": uuid.uuid4().hex,
            "email_confirm": True,
        }).user
        user_id = str(user.id)
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO _fd.user_roles (user_id, role) VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET role = EXCLUDED.role", (user_id, role),
            )
        db.commit()
    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = user_id
        session["email"] = user.email
    return user_id, client


def _add_rows(app, owner_id, experiment):
    """One well and one image linked to it, both owned by ``owner_id``."""
    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO _fd.imagehub_wells (owner_id, dataset, experiment, "
                "source_workbook, source_sheet, source_row, fields) "
                "VALUES (%s, %s, %s, %s, 'Sheet1', 1, %s::jsonb) RETURNING id",
                (owner_id, DATASET, experiment, f"{experiment}.xlsx",
                 f'{{"experiment": "{experiment}", "tissue": "tissue-{experiment}"}}'),
            )
            well_id = str(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO _fd.imagehub_images (owner_id, dataset, well_id, match_status, "
                "experiment, fields, source_zip, source_member, mime, original_name) "
                "VALUES (%s, %s, %s, 'matched', %s, '{\"vid\": \"1\", \"well\": \"A1\"}', "
                "%s, 'm/VID1_A1_1_00d01h00m.tif', 'image/tiff', 'VID1_A1_1_00d01h00m.tif') "
                "RETURNING id",
                (owner_id, DATASET, well_id, experiment, f"{experiment}.zip"),
            )
            image_id = str(cur.fetchone()[0])
        db.commit()
    return image_id, well_id


@pytest.fixture
def users(app, tmp_path, monkeypatch):
    # No zips on this disk: uploads report it, exports list the files as missing.
    monkeypatch.setattr(ingest, "DISK_ROOT", str(tmp_path))
    monkeypatch.setattr(routes_module, "DISK_ROOT", str(tmp_path))
    monkeypatch.setattr(export, "EXPORT_DIR", str(tmp_path / "exports"))
    token = uuid.uuid4().hex[:10]
    a_id, a = _new_user(app, "curator")
    b_id, b = _new_user(app, "curator")
    admin_id, admin = _new_user(app, "admin")
    a_image, a_well = _add_rows(app, a_id, f"own-a-{token}")
    b_image, b_well = _add_rows(app, b_id, f"own-b-{token}")

    yield {
        "a": a, "b": b, "admin": admin, "token": token,
        "a_image": a_image, "a_well": a_well, "b_image": b_image, "b_well": b_well,
    }

    ids = (a_id, b_id, admin_id)
    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            for table in ("exports", "images", "wells"):
                cur.execute(f"DELETE FROM _fd.imagehub_{table} WHERE owner_id = ANY(%s::uuid[])",
                            (list(ids),))
            cur.execute("DELETE FROM _fd.plugin_audit WHERE actor = ANY(%s::uuid[])", (list(ids),))
            cur.execute("DELETE FROM _fd.user_roles WHERE user_id = ANY(%s::uuid[])", (list(ids),))
        db.commit()
        for user_id in ids:
            supabase_extension.client.auth.admin.delete_user(user_id)


def _link(app, image_id, well_id):
    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("UPDATE _fd.imagehub_images SET well_id = %s WHERE id = %s",
                        (well_id, image_id))
        db.commit()


def _a_well_data(token):
    """Values of A's well that must not reach anyone but A and admins."""
    return (f"tissue-own-a-{token}", f"own-a-{token}.xlsx")


def _export_text(client, experiment):
    """Every file of the export zip of one group, as one string."""
    response = client.post("/imagehub/api/export",
                           json={"filter": {"dataset": DATASET, "experiment": experiment}})
    assert response.status_code == 201
    download = client.get(response.get_json()["download_url"])
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.data)) as archive:
        return "\n".join(archive.read(name).decode("utf-8", "replace")
                         for name in archive.namelist())


def _listed(client, experiment):
    response = client.get(f"/imagehub/api/images?dataset={DATASET}&experiment={experiment}")
    assert response.status_code == 200
    return [image["id"] for image in response.get_json()["images"]]


def test_a_user_does_not_see_another_users_images(users):
    b, token = users["b"], users["token"]
    assert _listed(b, f"own-a-{token}") == []
    assert _listed(b, f"own-b-{token}") == [users["b_image"]]

    page = b.get(f"/imagehub/ui?dataset={DATASET}")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    # Neither in the results nor among the filter choices.
    assert users["a_image"] not in html
    assert f"own-a-{token}" not in html
    assert f"own-b-{token}" in html

    assert b.get(f"/imagehub/api/images/{users['a_image']}").status_code == 403
    assert b.get(f"/imagehub/ui/images/{users['a_image']}").status_code == 403
    assert b.get(f"/imagehub/api/wells/{users['a_well']}").status_code == 403
    assert b.get(f"/imagehub/api/images/{users['b_image']}").status_code == 200
    assert b.get(f"/imagehub/ui/images/{users['b_image']}").status_code == 200
    assert b.get(f"/imagehub/api/wells/{users['b_well']}").status_code == 200
    assert b.get(f"/imagehub/api/images/{uuid.uuid4()}").status_code == 404


def test_the_image_page_hides_a_linked_well_someone_else_owns(app, users):
    """Matching links across owners: B's image may point to A's well. B sees that
    it is linked, not its data; admin sees the data."""
    _link(app, users["b_image"], users["a_well"])
    a_data = _a_well_data(users["token"])

    page = users["b"].get(f"/imagehub/ui/images/{users['b_image']}")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "someone else imported" in html
    assert not any(value in html for value in a_data)

    html = users["admin"].get(f"/imagehub/ui/images/{users['b_image']}").get_data(as_text=True)
    assert "someone else imported" not in html
    assert all(value in html for value in a_data)


def test_a_user_cannot_upload_another_users_images(users):
    b = users["b"]
    response = b.post("/imagehub/api/upload",
                      json={"image_ids": [users["b_image"], users["a_image"]]})
    assert response.status_code == 403
    assert response.get_json()["image_ids"] == [users["a_image"]]

    response = b.post("/imagehub/api/upload", json={"image_ids": [users["b_image"]]})
    assert response.status_code == 200
    assert response.get_json() == [{"id": users["b_image"], "status": "disk not connected"}]


def test_a_user_cannot_export_another_users_images(users):
    b, token = users["b"], users["token"]
    response = b.post("/imagehub/api/export",
                      json={"filter": {"dataset": DATASET, "experiment": f"own-a-{token}"}})
    assert response.status_code == 400
    assert response.get_json()["error"] == "no images match this filter"

    response = b.post("/imagehub/api/export",
                      json={"filter": {"dataset": DATASET, "experiment": f"own-b-{token}"}})
    assert response.status_code == 201
    assert [m["id"] for m in response.get_json()["missing"]] == [users["b_image"]]


def test_an_admin_sees_uploads_and_exports_everything(users):
    admin, token = users["admin"], users["token"]
    assert _listed(admin, f"own-a-{token}") == [users["a_image"]]
    assert _listed(admin, f"own-b-{token}") == [users["b_image"]]
    html = admin.get(f"/imagehub/ui?dataset={DATASET}").get_data(as_text=True)
    assert f"own-a-{token}" in html and f"own-b-{token}" in html
    for owner in ("a", "b"):
        assert admin.get(f"/imagehub/api/images/{users[owner + '_image']}").status_code == 200
        assert admin.get(f"/imagehub/ui/images/{users[owner + '_image']}").status_code == 200
        assert admin.get(f"/imagehub/api/wells/{users[owner + '_well']}").status_code == 200

    response = admin.post("/imagehub/api/upload",
                          json={"image_ids": [users["a_image"], users["b_image"]]})
    assert response.status_code == 200
    assert {r["id"] for r in response.get_json()} == {users["a_image"], users["b_image"]}

    response = admin.post("/imagehub/api/export",
                          json={"filter": {"dataset": DATASET, "experiment": f"own-a-{token}"}})
    assert response.status_code == 201
    assert [m["id"] for m in response.get_json()["missing"]] == [users["a_image"]]


def test_the_api_and_export_hide_a_linked_well_someone_else_owns(app, users):
    """B's image linked to A's well: B gets no values of that well from the list,
    the query page, a filter or an export. A (the owner) and admin do."""
    token = users["token"]
    _link(app, users["b_image"], users["a_well"])
    a_data = _a_well_data(token)
    b_group = f"own-b-{token}"

    response = users["b"].get(f"/imagehub/api/images?dataset={DATASET}&experiment={b_group}")
    [image] = response.get_json()["images"]
    assert image["id"] == users["b_image"] and image["match_status"] == "matched"
    assert image["sample"] is None
    assert not any(value in response.get_data(as_text=True) for value in a_data)
    html = users["b"].get(f"/imagehub/ui?dataset={DATASET}&experiment={b_group}").get_data(as_text=True)
    assert users["b_image"] in html and a_data[0] not in html
    # A filter on the well's value must not tell B what it is.
    assert _listed(users["b"], f"{b_group}&tissue={a_data[0]}") == []

    export_text = _export_text(users["b"], b_group)
    assert f"{b_group}.zip" in export_text and "matched" in export_text
    assert not any(value in export_text for value in a_data)

    response = users["admin"].get(f"/imagehub/api/images?dataset={DATASET}&experiment={b_group}")
    [image] = response.get_json()["images"]
    assert image["sample"]["tissue"] == a_data[0]
    assert _listed(users["admin"], f"{b_group}&tissue={a_data[0]}") == [users["b_image"]]
    assert all(value in _export_text(users["admin"], b_group) for value in a_data)

    # The owner of the well sees it on their own image.
    a_group = f"own-a-{token}"
    [image] = users["a"].get(f"/imagehub/api/images?dataset={DATASET}&experiment={a_group}"
                             ).get_json()["images"]
    assert image["sample"]["tissue"] == a_data[0]
    assert _listed(users["a"], f"{a_group}&tissue={a_data[0]}") == [users["a_image"]]
    assert all(value in _export_text(users["a"], a_group) for value in a_data)
