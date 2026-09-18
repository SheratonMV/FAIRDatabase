"""Tests for /model/runs/<id>/artifacts and /model/artifacts/<id>.

Supabase Storage is mocked: the catalog row + RBAC paths are what we want to
exercise here. Bytes never leave the test process.

The storage client is reached through ``kernel.storage`` after the Phase 4
plugin migration, so the mock is patched there (not in the plugin routes).
"""
from __future__ import annotations

import io
from unittest.mock import patch, MagicMock

import pytest

from app import get_db


# ``Client.storage`` is a read-only property (lazily builds and caches a
# storage client on ``Client._storage``) in the installed supabase-py
# version, so it can't be ``patch()``-ed directly — patch the writable
# backing field it reads from instead.
_STORAGE_TARGET = "kernel.storage.supabase_extension.client._storage"


# ── helpers ───────────────────────────────────────────────────────────────────

def _seed_run(app, owner_id: str, created_by: str) -> tuple[int, int]:
    """Insert a parameter set + simulation run owned by ``owner_id``."""
    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO _fd.pbpk_parameter_sets (name, params, created_by, owner_id) "
            "VALUES ('artifact-test', '{}'::jsonb, %s, %s) RETURNING id",
            (created_by, owner_id),
        )
        ps_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO _fd.pbpk_simulation_runs "
            "(param_set_id, scenario, status, created_by, owner_id) "
            "VALUES (%s, 'no_bf', 'done', %s, %s) RETURNING id",
            (ps_id, created_by, owner_id),
        )
        run_id = cur.fetchone()[0]
        db.commit()
        cur.close()
    return ps_id, run_id


def _cleanup(app, ps_id: int, run_id: int) -> None:
    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute("DELETE FROM _fd.pbpk_run_artifacts WHERE run_id = %s", (run_id,))
        cur.execute("DELETE FROM _fd.pbpk_simulation_runs WHERE id = %s", (run_id,))
        cur.execute("DELETE FROM _fd.pbpk_parameter_sets WHERE id = %s", (ps_id,))
        db.commit()
        cur.close()


def _mock_storage():
    """Build a mocked supabase storage client that records calls."""
    bucket = MagicMock()
    bucket.upload.return_value = {"Key": "ok"}
    bucket.remove.return_value = {"data": []}
    bucket.create_signed_url.return_value = {"signedURL": "https://signed.example/x"}
    storage = MagicMock()
    storage.from_.return_value = bucket
    return storage, bucket


# ── tests ─────────────────────────────────────────────────────────────────────

class TestArtifactRoutes:
    def test_curator_can_upload_own_run(self, curator_user, app):
        client, user = curator_user
        ps_id, run_id = _seed_run(app, owner_id=str(user.id), created_by=user.email)
        try:
            storage, bucket = _mock_storage()
            with patch(_STORAGE_TARGET, new=storage):
                resp = client.post(
                    f"/model/runs/{run_id}/artifacts",
                    data={"file": (io.BytesIO(b"\x89PNG\r\n\x1a\nfake"), "fig.png")},
                    content_type="multipart/form-data",
                )
            assert resp.status_code == 201, resp.get_json()
            body = resp.get_json()
            assert body["kind"] == "image"
            assert body["mime"] == "image/png"
            assert body["original_name"] == "fig.png"
            assert body["storage_path"].startswith("pbpk-artifacts/")
            bucket.upload.assert_called_once()
        finally:
            _cleanup(app, ps_id, run_id)

    def test_upload_oversize_returns_413(self, curator_user, app):
        client, user = curator_user
        ps_id, run_id = _seed_run(app, owner_id=str(user.id), created_by=user.email)
        try:
            storage, _ = _mock_storage()
            big = b"\x00" * (200 * 1024 * 1024 + 1)
            with patch(_STORAGE_TARGET, new=storage):
                resp = client.post(
                    f"/model/runs/{run_id}/artifacts",
                    data={"file": (io.BytesIO(big), "big.png")},
                    content_type="multipart/form-data",
                )
            assert resp.status_code == 413
        finally:
            _cleanup(app, ps_id, run_id)

    def test_upload_bad_mime_returns_400(self, curator_user, app):
        client, user = curator_user
        ps_id, run_id = _seed_run(app, owner_id=str(user.id), created_by=user.email)
        try:
            storage, _ = _mock_storage()
            with patch(_STORAGE_TARGET, new=storage):
                resp = client.post(
                    f"/model/runs/{run_id}/artifacts",
                    data={"file": (io.BytesIO(b"not really exe"), "thing.exe")},
                    content_type="multipart/form-data",
                )
            assert resp.status_code == 400
        finally:
            _cleanup(app, ps_id, run_id)

    def test_upload_extension_mime_mismatch_returns_400(self, curator_user, app):
        """Filename says .png but caller claims image/jpeg → reject."""
        client, user = curator_user
        ps_id, run_id = _seed_run(app, owner_id=str(user.id), created_by=user.email)
        try:
            storage, _ = _mock_storage()
            with patch(_STORAGE_TARGET, new=storage):
                # werkzeug infers mimetype from the filename's extension by
                # default, so we have to pass it explicitly to force the
                # mismatch we care about.
                from werkzeug.datastructures import FileStorage
                fs = FileStorage(
                    stream=io.BytesIO(b"abc"),
                    filename="lying.png",
                    content_type="image/jpeg",
                )
                resp = client.post(
                    f"/model/runs/{run_id}/artifacts",
                    data={"file": fs},
                    content_type="multipart/form-data",
                )
            assert resp.status_code == 400
            assert "extension" in resp.get_json()["error"]
        finally:
            _cleanup(app, ps_id, run_id)

    def test_upload_to_other_users_run_returns_403(self, curator_user, app):
        client, user = curator_user
        # Owner is a different uuid; created_by intentionally set to the test
        # user's email so the row is recoverable but not owned by them.
        other_owner = "00000000-0000-0000-0000-0000000000aa"
        ps_id, run_id = _seed_run(app, owner_id=other_owner, created_by=user.email)
        try:
            storage, _ = _mock_storage()
            with patch(_STORAGE_TARGET, new=storage):
                resp = client.post(
                    f"/model/runs/{run_id}/artifacts",
                    data={"file": (io.BytesIO(b"x"), "fig.png")},
                    content_type="multipart/form-data",
                )
            assert resp.status_code == 403
        finally:
            _cleanup(app, ps_id, run_id)

    def test_delete_removes_catalog_row(self, curator_user, app):
        client, user = curator_user
        ps_id, run_id = _seed_run(app, owner_id=str(user.id), created_by=user.email)
        try:
            storage, bucket = _mock_storage()
            with patch(_STORAGE_TARGET, new=storage):
                up = client.post(
                    f"/model/runs/{run_id}/artifacts",
                    data={"file": (io.BytesIO(b"abc"), "fig.png")},
                    content_type="multipart/form-data",
                )
                assert up.status_code == 201
                artifact_id = up.get_json()["id"]

                d = client.delete(f"/model/artifacts/{artifact_id}")
                assert d.status_code == 200
                assert d.get_json()["deleted"] == artifact_id
                bucket.remove.assert_called_once()

            with app.app_context():
                db = get_db()
                cur = db.cursor()
                cur.execute(
                    "SELECT 1 FROM _fd.pbpk_run_artifacts WHERE id = %s",
                    (artifact_id,),
                )
                assert cur.fetchone() is None
                cur.close()
        finally:
            _cleanup(app, ps_id, run_id)

    def test_delete_proceeds_when_blob_remove_fails(self, curator_user, app):
        """Storage flake should not block catalog cleanup."""
        client, user = curator_user
        ps_id, run_id = _seed_run(app, owner_id=str(user.id), created_by=user.email)
        try:
            storage, bucket = _mock_storage()
            with patch(_STORAGE_TARGET, new=storage):
                up = client.post(
                    f"/model/runs/{run_id}/artifacts",
                    data={"file": (io.BytesIO(b"abc"), "fig.png")},
                    content_type="multipart/form-data",
                )
                artifact_id = up.get_json()["id"]
                bucket.remove.side_effect = RuntimeError("storage offline")
                d = client.delete(f"/model/artifacts/{artifact_id}")
                assert d.status_code == 200

            with app.app_context():
                db = get_db()
                cur = db.cursor()
                cur.execute(
                    "SELECT 1 FROM _fd.pbpk_run_artifacts WHERE id = %s",
                    (artifact_id,),
                )
                assert cur.fetchone() is None
                cur.close()
        finally:
            _cleanup(app, ps_id, run_id)

    def test_list_artifacts_for_other_users_run_returns_403(self, curator_user, app):
        client, user = curator_user
        other_owner = "00000000-0000-0000-0000-0000000000bb"
        ps_id, run_id = _seed_run(app, owner_id=other_owner, created_by=user.email)
        try:
            resp = client.get(f"/model/runs/{run_id}/artifacts")
            assert resp.status_code == 403
        finally:
            _cleanup(app, ps_id, run_id)
