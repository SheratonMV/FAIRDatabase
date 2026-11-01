"""Handlers for the admin and grants console.

These mirror the request/handler split used elsewhere in the project (see
``src/dashboard/`` and ``src/data/``). Each handler builds a ``ctx`` dict for
its template and performs the underlying DB / Supabase work.
"""

from flask import g, session

from config import get_db, supabase_extension

import logging
_log = logging.getLogger(__name__)


ALLOWED_ROLES = ("admin", "curator", "accessor", "visualizer")


def list_supabase_users(client=None, page_size=200, max_pages=50):
    """Return a list of (id, email) for **all** Supabase auth users.

    Walks pages until an empty/short page is returned. ``page_size=200`` is
    Supabase's max-per-page; ``max_pages`` caps the walk at 10k users to avoid
    runaway pagination if the API ever stops short-circuiting.

    ``client`` is optional so callers outside a Flask request context (e.g. the
    boot-time ``_bootstrap_admin``) can pass their own service-role client.
    Best-effort: returns an empty list if the admin API is unavailable.
    """
    if client is None:
        try:
            client = supabase_extension.client
        except Exception:
            return []

    out = []
    seen_ids = set()
    for page in range(1, max_pages + 1):
        try:
            users = client.auth.admin.list_users(page=page, per_page=page_size)
        except TypeError:
            # Older SDKs don't accept kwargs; fall back to the unpaginated call
            # and trust whatever it returns.
            try:
                users = client.auth.admin.list_users()
            except Exception:
                break
            users = users or []
            for u in users:
                uid = getattr(u, "id", None)
                email = getattr(u, "email", None) or ""
                if uid and str(uid) not in seen_ids:
                    seen_ids.add(str(uid))
                    out.append((str(uid), email))
            return out
        except Exception:
            break

        users = users or []
        if not users:
            break
        for u in users:
            uid = getattr(u, "id", None)
            email = getattr(u, "email", None) or ""
            if uid and str(uid) not in seen_ids:
                seen_ids.add(str(uid))
                out.append((str(uid), email))
        if len(users) < page_size:
            break
    return out


# Backwards-compatible private alias used by the handlers below.
_list_supabase_users = list_supabase_users


class UserListHandler:
    """Build the admin user list with current role assignments."""

    def __init__(self):
        self._ctx = {
            "user_email": session.get("email"),
            "current_path": "/admin/users",
            "users": [],
            "allowed_roles": ALLOWED_ROLES,
            "current_user_id": session.get("user"),
        }

    def load(self):
        users = _list_supabase_users()
        roles = {}
        if users:
            db = get_db()
            if db is not None:
                with db.cursor() as cur:
                    cur.execute(
                        "SELECT user_id::text, role::text FROM _fd.user_roles"
                    )
                    roles = dict(cur.fetchall())
        self._ctx["users"] = [
            {
                "id": uid,
                "email": email,
                "role": roles.get(uid, "visualizer"),
            }
            for uid, email in sorted(users, key=lambda u: u[1] or "")
        ]
        return self

    @property
    def ctx(self):
        return self._ctx


class RoleAssignHandler:
    """Persist a role change and append a row to ``_fd.role_audit``."""

    def __init__(self, target_user_id, new_role):
        self.target_user_id = str(target_user_id)
        self.new_role = (new_role or "").strip().lower()

    def apply(self):
        if self.new_role not in ALLOWED_ROLES:
            return False, f"Unknown role: {self.new_role}"

        db = get_db()
        if db is None:
            return False, "Database unavailable."

        changed_by = session.get("user")
        try:
            with db.cursor() as cur:
                cur.execute(
                    "SELECT role::text FROM _fd.user_roles WHERE user_id = %s",
                    (self.target_user_id,),
                )
                row = cur.fetchone()
                old_role = row[0] if row else None

                if old_role == self.new_role:
                    db.commit()
                    return True, "No change."

                cur.execute(
                    "INSERT INTO _fd.user_roles (user_id, role, assigned_by) "
                    "VALUES (%s, %s::_fd.user_role, %s) "
                    "ON CONFLICT (user_id) DO UPDATE "
                    "SET role = EXCLUDED.role, "
                    "    assigned_by = EXCLUDED.assigned_by, "
                    "    assigned_at = now()",
                    (self.target_user_id, self.new_role, changed_by),
                )
                cur.execute(
                    "INSERT INTO _fd.role_audit "
                    "(user_id, old_role, new_role, changed_by) VALUES "
                    "(%s, %s::_fd.user_role, %s::_fd.user_role, %s)",
                    (self.target_user_id, old_role, self.new_role, changed_by),
                )
            db.commit()
            return True, f"Role updated to {self.new_role}."
        except Exception as exc:
            db.rollback()
            _log.exception("role update failed")
            return False, "Role update failed."


class GrantsHandler:
    """List and mutate per-dataset grants.

    Admins can manage any dataset; curators can manage only datasets they
    own. Authorisation is checked here rather than on the route so the same
    handler can power both the admin and curator entry points later.
    """

    def __init__(self, dataset_id):
        self.dataset_id = int(dataset_id)
        self._ctx = {
            "user_email": session.get("email"),
            "current_path": f"/admin/datasets/{self.dataset_id}/grants",
            "current_user_id": session.get("user"),
            "dataset": None,
            "grants": [],
            "candidate_users": [],
            "allowed": False,
        }

    def _check_access(self, cur):
        cur.execute(
            "SELECT id, table_name, main_table, owner_id::text "
            "FROM _fd.metadata_tables WHERE id = %s",
            (self.dataset_id,),
        )
        ds = cur.fetchone()
        if ds is None:
            return None, False
        owner_id = ds[3]
        role = getattr(g, "role", None)
        user_id = getattr(g, "user", None)
        if role == "admin":
            return ds, True
        if role == "curator" and owner_id == str(user_id):
            return ds, True
        return ds, False

    def load(self):
        db = get_db()
        if db is None:
            return self
        with db.cursor() as cur:
            ds, allowed = self._check_access(cur)
            if ds is None or not allowed:
                self._ctx["allowed"] = allowed
                self._ctx["dataset"] = (
                    {"id": ds[0], "table_name": ds[1], "main_table": ds[2]}
                    if ds else None
                )
                return self

            cur.execute(
                "SELECT user_id::text, granted_by::text, granted_at "
                "FROM _fd.dataset_grants WHERE dataset_id = %s "
                "ORDER BY granted_at DESC",
                (self.dataset_id,),
            )
            grant_rows = cur.fetchall()

        users = _list_supabase_users()
        email_by_id = {uid: email for uid, email in users}
        granted_ids = {row[0] for row in grant_rows}

        self._ctx["allowed"] = True
        self._ctx["dataset"] = {
            "id": ds[0], "table_name": ds[1], "main_table": ds[2],
        }
        self._ctx["grants"] = [
            {
                "user_id": uid,
                "email": email_by_id.get(uid, "(unknown)"),
                "granted_by_email": email_by_id.get(by, "(unknown)"),
                "granted_at": at,
            }
            for uid, by, at in grant_rows
        ]
        self._ctx["candidate_users"] = [
            {"id": uid, "email": email}
            for uid, email in users
            if uid not in granted_ids and uid != self._ctx.get("current_user_id")
        ]
        return self

    def grant(self, target_user_id):
        target_user_id = str(target_user_id or "").strip()
        if not target_user_id:
            return False, "Missing user."
        db = get_db()
        if db is None:
            return False, "Database unavailable."
        try:
            with db.cursor() as cur:
                _, allowed = self._check_access(cur)
                if not allowed:
                    return False, "Forbidden."
                cur.execute(
                    "INSERT INTO _fd.dataset_grants "
                    "(dataset_id, user_id, granted_by) VALUES (%s, %s, %s) "
                    "ON CONFLICT (dataset_id, user_id) DO NOTHING",
                    (self.dataset_id, target_user_id, session.get("user")),
                )
                cur.execute(
                    "INSERT INTO _fd.grant_audit "
                    "(dataset_id, user_id, action, changed_by) VALUES "
                    "(%s, %s, %s, %s)",
                    (self.dataset_id, target_user_id, "granted", session.get("user")),
                )
            db.commit()
            return True, "Access granted."
        except Exception as exc:
            db.rollback()
            _log.exception("grant failed")
            return False, "Grant failed."

    def revoke(self, target_user_id):
        target_user_id = str(target_user_id or "").strip()
        if not target_user_id:
            return False, "Missing user."
        db = get_db()
        if db is None:
            return False, "Database unavailable."
        try:
            with db.cursor() as cur:
                _, allowed = self._check_access(cur)
                if not allowed:
                    return False, "Forbidden."
                cur.execute(
                    "DELETE FROM _fd.dataset_grants "
                    "WHERE dataset_id = %s AND user_id = %s",
                    (self.dataset_id, target_user_id),
                )
                if cur.rowcount:
                    cur.execute(
                        "INSERT INTO _fd.grant_audit "
                        "(dataset_id, user_id, action, changed_by) VALUES "
                        "(%s, %s, %s, %s)",
                        (self.dataset_id, target_user_id, "revoked", session.get("user")),
                    )
            db.commit()
            return True, "Access revoked."
        except Exception as exc:
            db.rollback()
            _log.exception("revoke failed")
            return False, "Revoke failed."

    @property
    def ctx(self):
        return self._ctx
