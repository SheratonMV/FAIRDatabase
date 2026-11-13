"""The invented leaf disc dataset with extra image fields, for the database tests.

Synthetic only: tests/leaf.py makes the workbook and the zip in the test's temporary
folder. Every row is owned by temporary users and removed afterwards.
"""
import copy
import uuid

from app import get_db
from config import supabase_extension
from plugins.imagehub import cli, config, export, ingest, routes as routes_module
from plugins.imagehub.tests import leaf

EXTRA_FIELDS = {
    "disc_area": {"type": "float", "label": "Disc area", "unit": "mm2", "decimals": 1},
    "lesions": {"type": "int", "label": "Lesions"},
}


def raw(dataset_id, extra=True):
    """The leaf config under its own id; with ``extra``, the extra fields in the ui,
    the image details and the export."""
    out = copy.deepcopy(leaf.dataset().raw)
    out["id"] = dataset_id
    if not extra:
        return out
    out["images"]["extra_fields"] = copy.deepcopy(EXTRA_FIELDS)
    ui = out["ui"]
    ui["filters"].append({"field": "image.disc_area", "type": "range",
                          "params": ["area_from", "area_to"], "labels": ["Area from", "Area to"]})
    ui["sort"] = ["image.disc_area"] + ui["sort"]
    ui["columns"].append({"label": "Disc area", "field": "image.disc_area"})
    ui["image_details"].append({"label": "Disc area", "field": "image.disc_area"})
    out["export"]["sections"][0]["columns"].append(
        {"name": "disc_area", "from": "image.disc_area", "description": "Disc area in mm2"})
    return out


def _user(app, role, token, label):
    with app.app_context():
        email = f"imagehub-extra-{label}-{token}@test.com"
        user_id = str(supabase_extension.client.auth.admin.create_user({
            "email": email, "password": uuid.uuid4().hex, "email_confirm": True,
        }).user.id)
        db = get_db()
        with db.cursor() as cur:
            cur.execute("INSERT INTO _fd.user_roles (user_id, role) VALUES (%s, %s) "
                        "ON CONFLICT (user_id) DO UPDATE SET role = EXCLUDED.role", (user_id, role))
        db.commit()
    return user_id, email


def world(app, tmp_path, monkeypatch):
    """Generator for a fixture: one dataset, two users (A loads it, B owns one image)."""
    token = uuid.uuid4().hex[:10]
    disk = tmp_path / "disk"
    disk.mkdir()
    book = leaf.make_workbook(tmp_path / "leaves.xlsx")
    leaf.make_disk(str(disk))
    for module in (ingest, routes_module, cli):
        monkeypatch.setattr(module, "DISK_ROOT", str(disk))
    monkeypatch.setattr(cli, "REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(export, "EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("IMAGEHUB_PUBLIC_STORAGE_URL", "http://kong:8000")
    dataset_id = f"leaf_extra_{token}"
    state = {}

    def use(extra=True):
        ds = config.Dataset(raw(dataset_id, extra), f"leaf extra {token}")
        state["ds"] = ds
        monkeypatch.setattr(config, "datasets", lambda: {ds.id: ds})
        monkeypatch.setenv("IMAGEHUB_DATASET", ds.id)
        return ds

    use()
    a_id, a_email = _user(app, "admin", token, "a")
    b_id, b_email = _user(app, "curator", token, "b")
    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = a_id

    def invoke(*args):
        return app.test_cli_runner().invoke(args=["imagehub", *args])

    def run(*args):
        result = invoke(*args)
        assert result.exit_code == 0, f"{args}: {result.output}\n{result.exception!r}"
        return result.output

    def sql(statement, *params, commit=False):
        with app.app_context():
            db = get_db()
            with db.cursor() as cur:
                cur.execute(statement, params)
                rows = cur.fetchall() if cur.description else []
            db.commit() if commit else db.rollback()
        return rows

    def load():
        run("import-metadata", "--dataset", dataset_id, "--source", str(book),
            "--apply", "--as", a_email)
        return run("catalog", "--dataset", dataset_id, "--apply", "--as", a_email)

    yield {"app": app, "client": client, "dataset_id": dataset_id, "token": token,
           "a_id": a_id, "a_email": a_email, "b_id": b_id, "b_email": b_email,
           "use": use, "state": state, "invoke": invoke, "run": run, "sql": sql, "load": load}

    users = [a_id, b_id]
    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            for table in ("exports", "annotations", "images", "wells", "legends"):
                cur.execute(f"DELETE FROM _fd.imagehub_{table} WHERE owner_id = ANY(%s::uuid[])", (users,))
            cur.execute("DELETE FROM _fd.plugin_audit WHERE actor = ANY(%s::uuid[])", (users,))
            cur.execute("DELETE FROM _fd.user_roles WHERE user_id = ANY(%s::uuid[])", (users,))
        db.commit()
        for user_id in users:
            supabase_extension.client.auth.admin.delete_user(user_id)
