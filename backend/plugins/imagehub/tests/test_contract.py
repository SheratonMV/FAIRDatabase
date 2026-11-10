"""The plugin contract: roles, ownership, audit, delete, migrations, boundaries."""
import os
import re
import uuid

import pytest

from app import get_db
from config import supabase_extension
from plugins.imagehub.plugin import PLUGIN
from plugins.imagehub.query import main as query_main

from .test_image_flow import stack  # noqa: F401 (fixture)

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GONE = str(uuid.uuid4())
READ = {"admin", "curator", "accessor"}
WRITE = {"admin", "curator"}
# method, path, who may pass the role check. A row that does not exist gives 404
# after that check, so nothing real is touched.
ROUTES = [
    ("get", "/imagehub/ui", READ),
    ("get", f"/imagehub/ui/images/{GONE}", READ),
    ("get", "/imagehub/api/images?experiment=none", READ),
    ("get", f"/imagehub/api/images/{GONE}", READ),
    ("get", f"/imagehub/api/wells/{GONE}", READ),
    ("post", "/imagehub/api/upload", WRITE),
    ("post", "/imagehub/api/export", WRITE),
    ("get", f"/imagehub/api/exports/{GONE}/download", WRITE),
    ("delete", f"/imagehub/api/images/{GONE}", WRITE),
    ("delete", f"/imagehub/api/annotations/{GONE}", WRITE),
    ("delete", f"/imagehub/api/wells/{GONE}", WRITE),
    ("delete", f"/imagehub/api/exports/{GONE}", WRITE),
]


def test_every_route_is_in_the_matrix(app):
    declared = {
        rule.rule for rule in app.url_map.iter_rules()
        if rule.endpoint.startswith("imagehub_routes.")
    }
    normalised = {re.sub(r"[0-9a-f-]{36}", "<id>", path.split("?")[0]) for _, path, _ in ROUTES}
    assert {re.sub(r"<uuid:\w+>", "<id>", rule) for rule in declared} == normalised


@pytest.mark.parametrize("role", ["admin", "curator", "accessor", "visualizer"])
def test_role_matrix(stack, role):  # noqa: F811
    stack["set_role"](role)
    client = stack["client"]
    for method, path, allowed in ROUTES:
        kwargs = {"json": {}} if method != "get" else {}
        status = getattr(client, method)(path, **kwargs).status_code
        if role in allowed:
            assert status != 403, f"{role} {method} {path}"
            assert status < 500, f"{role} {method} {path}: {status}"
        else:
            assert status == 403, f"{role} {method} {path}: {status}"


def test_not_logged_in_is_redirected(app):
    client = app.test_client()
    for method, path, _ in ROUTES:
        kwargs = {"json": {}} if method != "get" else {}
        assert getattr(client, method)(path, **kwargs).status_code == 302, path


def test_curator_cannot_delete_what_someone_else_owns(stack):  # noqa: F811
    app, client, image_id = stack["app"], stack["client"], stack["image_id"]
    with app.app_context():
        other = supabase_extension.client.auth.admin.create_user({
            "email": f"imagehub-other-{uuid.uuid4().hex[:10]}@test.com",
            "password": uuid.uuid4().hex, "email_confirm": True,
        }).user
        db = get_db()
        with db.cursor() as cur:
            cur.execute("UPDATE _fd.imagehub_images SET owner_id = %s WHERE id = %s", (str(other.id), image_id))
        db.commit()
    try:
        stack["set_role"]("curator")
        assert client.delete(f"/imagehub/api/images/{image_id}", json={}).status_code == 403
        assert client.get(f"/imagehub/api/images/{image_id}").status_code == 403
        stack["set_role"]("admin")
        assert client.get(f"/imagehub/api/images/{image_id}").status_code == 200
        assert client.delete(f"/imagehub/api/images/{image_id}", json={}).status_code == 200
    finally:
        with app.app_context():
            db = get_db()
            with db.cursor() as cur:
                cur.execute("DELETE FROM _fd.imagehub_images WHERE id = %s", (image_id,))
            db.commit()
            supabase_extension.client.auth.admin.delete_user(other.id)


def test_deleting_a_well_keeps_its_images_unlinked(stack):  # noqa: F811
    app, client, image_id = stack["app"], stack["client"], stack["image_id"]
    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO _fd.imagehub_wells (owner_id, dataset, source_workbook, source_sheet, "
                "source_row, fields, props) VALUES (%s, 'spheroid_example', 'synthetic.xlsx', "
                "'S', 2, '{\"vid\": \"1\", \"well\": \"A1\"}', '{\"x\": 1}') RETURNING id",
                (stack["user_id"],),
            )
            well_id = str(cur.fetchone()[0])
            cur.execute("UPDATE _fd.imagehub_images SET well_id = %s, match_status = 'matched' WHERE id = %s", (well_id, image_id))
        db.commit()
    assert client.get(f"/imagehub/api/wells/{well_id}").get_json()["props"] == {"x": 1}
    response = client.delete(f"/imagehub/api/wells/{well_id}", json={})
    assert response.get_json()["images_unlinked"] == 1
    assert client.get(f"/imagehub/api/wells/{well_id}").status_code == 404
    image = client.get(f"/imagehub/api/images/{image_id}").get_json()
    assert image["well_id"] is None and image["match_status"] == "unmatched"


def test_migrations_can_run_twice(app):
    with app.app_context():
        db = get_db()
        try:
            with db.cursor() as cur:
                for _ in range(2):
                    for name in PLUGIN.sql_migrations:
                        with open(os.path.join(PLUGIN_DIR, name), encoding="utf-8") as fh:
                            cur.execute(fh.read())
        finally:
            db.rollback()


def test_manifest_follows_the_contract():
    assert PLUGIN.name == "imagehub" and PLUGIN.table_prefix == "imagehub_"
    assert PLUGIN.nav["label"] == "Image hub"
    bucket = PLUGIN.storage_buckets[0]
    assert bucket["id"] == "imagehub-images" and bucket["public"] is False
    assert {"image/jpeg", "image/png", "image/tiff", "application/json"} == bucket["mime_whitelist"]
    assert bucket["size_limit"] == 50 * 1024 * 1024


def test_every_table_has_the_required_columns(app):
    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "SELECT table_name, array_agg(column_name::text) FROM information_schema.columns "
                "WHERE table_schema = '_fd' AND table_name LIKE 'imagehub\\_%%' GROUP BY 1"
            )
            tables = dict(cur.fetchall())
        db.rollback()
    assert set(tables) == {
        "imagehub_wells", "imagehub_images", "imagehub_annotations", "imagehub_legends", "imagehub_exports",
    }
    for table, columns in tables.items():
        assert {"id", "owner_id", "created_at", "updated_at"} <= set(columns), table


def _source_files():
    for folder, _, names in os.walk(PLUGIN_DIR):
        if "__pycache__" in folder or os.sep + "tests" in folder:
            continue
        for name in names:
            if name.endswith(".py"):
                yield os.path.join(folder, name)


def test_plugin_code_imports_only_the_kernel():
    pattern = re.compile(r"^\s*(?:from|import)\s+(src|config|app|plugins)\b", re.MULTILINE)
    for path in _source_files():
        with open(path, encoding="utf-8") as fh:
            assert not pattern.search(fh.read()), path


def test_plugin_code_does_not_read_the_environment_directly():
    for path in _source_files():
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert "os.getenv" not in text and "os.environ" not in text, path


def test_the_disk_is_only_opened_for_reading():
    for path in _source_files():
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert not re.search(r"ZipFile\([^)]*DISK_ROOT[^)]*[\"'][wax][\"']", text), path
    with open(os.path.join(PLUGIN_DIR, "ingest.py"), encoding="utf-8") as fh:
        assert 'ZipFile(path, "w"' not in fh.read()


def test_git_rules_block_real_data():
    with open(os.path.join(PLUGIN_DIR, ".gitignore"), encoding="utf-8") as fh:
        rules = fh.read()
    for pattern in ("*.xlsx", "*.json", "*.jpg", "*.tif", "*.csv", "*.zip", "*.fcs"):
        assert pattern in rules


needs_role = pytest.mark.skipif(
    not os.getenv("IMAGEHUB_RO_PASSWORD"), reason="IMAGEHUB_RO_PASSWORD is not set",
)


@needs_role
def test_query_cli_prints_a_table_and_csv(capsys):
    assert query_main(["SELECT 1 AS a, 'x, y' AS b"]) == 0
    out = capsys.readouterr()
    assert "a | b" in out.out and "(1 rows)" in out.err
    assert query_main(["--format", "csv", "SELECT 1 AS a, 'x, y' AS b"]) == 0
    assert capsys.readouterr().out.splitlines() == ["a,b", '1,"x, y"']


@needs_role
def test_query_cli_applies_the_limit(capsys):
    assert query_main(["--limit", "2", "SELECT generate_series(1, 5) AS n"]) == 0
    out = capsys.readouterr()
    assert "cut off at the limit" in out.err and "5" not in out.out


@needs_role
@pytest.mark.parametrize("sql,message", [
    ("DELETE FROM _fd.imagehub_wells", "only SELECT"),
    ("SELECT 1; SELECT 2", "one statement"),
    ("SELECT * FROM auth.users", "permission denied"),
    ("SELECT * FROM _fd.user_roles", "permission denied"),
])
def test_query_cli_refuses_with_a_clear_error(capsys, sql, message):
    assert query_main([sql]) == 1
    assert message in capsys.readouterr().err
