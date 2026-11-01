"""ADMIN_EMAIL promotion must not trust an address Supabase never verified.

With e-mail auto-confirm on, anyone can register ADMIN_EMAIL and it shows as
confirmed instantly, so _bootstrap_admin must refuse unless auto-confirm is
visibly off (or the local-only override is set). Supabase and Postgres are
stubbed: the test only watches whether a promotion is attempted."""

import types

import pytest

import app as app_module

UID = "11111111-1111-1111-1111-111111111111"


class _Cur:
    def __init__(self, log): self.log = log
    def execute(self, sql, params=()): self.log.append(sql)
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Conn:
    def __init__(self, log): self.log = log
    def cursor(self): return _Cur(self.log)
    def commit(self): pass
    def close(self): pass


@pytest.fixture
def run_bootstrap(monkeypatch):
    def _run(env, confirmed=True):
        for k in ("ENABLE_EMAIL_AUTOCONFIRM", "ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("ADMIN_EMAIL", "boss@lab.org")
        for k, v in env.items():
            monkeypatch.setenv(k, v)

        user = types.SimpleNamespace(
            email_confirmed_at="2026-01-01T00:00:00Z" if confirmed else None
        )
        client = types.SimpleNamespace(auth=types.SimpleNamespace(admin=types.SimpleNamespace(
            get_user_by_id=lambda uid: types.SimpleNamespace(user=user))))
        monkeypatch.setattr(app_module, "create_client", lambda *a: client)
        import src.admin.form as admin_form
        monkeypatch.setattr(admin_form, "list_supabase_users",
                            lambda client=None: [(UID, "boss@lab.org")])
        sql_log = []
        monkeypatch.setattr(app_module.psycopg2, "connect", lambda **kw: _Conn(sql_log))

        fake_app = types.SimpleNamespace(
            config={"SUPABASE_URL": "http://x", "SUPABASE_SERVICE_ROLE_KEY": "k",
                    "POSTGRES_HOST": "h", "POSTGRES_PORT": 1, "POSTGRES_USER": "u",
                    "POSTGRES_PASSWORD": "p", "POSTGRES_DB_NAME": "d"},
            logger=types.SimpleNamespace(info=lambda *a: None, warning=lambda *a: None),
        )
        app_module._bootstrap_admin(fake_app)
        return any("user_roles" in s for s in sql_log)

    return _run


def test_autoconfirm_on_blocks_promotion(run_bootstrap):
    assert run_bootstrap({"ENABLE_EMAIL_AUTOCONFIRM": "true"}) is False


def test_autoconfirm_unset_blocks_promotion(run_bootstrap):
    assert run_bootstrap({}) is False


def test_autoconfirm_off_and_confirmed_promotes(run_bootstrap):
    assert run_bootstrap({"ENABLE_EMAIL_AUTOCONFIRM": "false"}) is True


def test_autoconfirm_off_but_unconfirmed_blocks(run_bootstrap):
    assert run_bootstrap({"ENABLE_EMAIL_AUTOCONFIRM": "false"}, confirmed=False) is False


def test_local_override_allows_promotion(run_bootstrap):
    assert run_bootstrap({"ENABLE_EMAIL_AUTOCONFIRM": "true",
                          "ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM": "true"}) is True
