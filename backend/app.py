"""Main application of the Flask API. Registers all blueprints and then
starts the server."""

import os

import psycopg2
from flask import Flask, json, g, url_for, redirect, flash, request
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from supabase import create_client

from config import Config, supabase_extension, limiter, get_db, teardown_db
from kernel.loader import (
    discover_plugins,
    register_plugins,
    apply_plugin_schema,
    bootstrap_plugin_buckets,
)
from src.exceptions import GenericExceptionHandler
from src.csrf import init_csrf
from src.auth.routes import routes as auth_routes
from src.dashboard.routes import routes as dashboard_routes
from src.data.routes import routes as data_routes
from src.privacy.routes import routes as privacy_routes
from src.main.routes import routes as main_routes
from src.visualization.routes import routes as visualization_routes
from src.admin.routes import routes as admin_routes
from src.demo.routes import routes as demo_routes

from config import load_settings, require_strong_secret_key


def _bootstrap_admin(app):
    """Promote the user identified by ADMIN_EMAIL to the 'admin' role.

    Idempotent and best-effort: silently no-op if the env var is missing, the
    Supabase service role key is unavailable, or the user has not yet
    registered. Re-runs on every boot so that newly registering admins are
    promoted as soon as their account exists.
    """
    admin_email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    if not admin_email:
        return

    # Promotion trusts "this address is confirmed". With e-mail auto-confirm
    # on, Supabase marks every signup confirmed without sending anything, so
    # a stranger who registers ADMIN_EMAIL first would become admin. Refuse
    # unless auto-confirm is visibly off. If the setting is missing, Flask
    # cannot tell, so refuse as well. An existing admin keeps the role either
    # way; this only blocks new promotions. For a local machine nobody else
    # can reach, ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM=true lifts the refusal.
    autoconfirm = (os.getenv("ENABLE_EMAIL_AUTOCONFIRM") or "").strip().lower()
    allow_local = (
        os.getenv("ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM", "").strip().lower() == "true"
    )
    if autoconfirm != "false" and not allow_local:
        app.logger.warning(
            "Not promoting ADMIN_EMAIL=%s: ENABLE_EMAIL_AUTOCONFIRM is %r, so "
            "Supabase does not verify that the address belongs to whoever "
            "registered it. Set ENABLE_EMAIL_AUTOCONFIRM=false (needs SMTP), "
            "or ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM=true on a local-only setup.",
            admin_email, autoconfirm or "unset",
        )
        return

    url = app.config.get("SUPABASE_URL")
    service_key = app.config.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not service_key:
        return

    try:
        from src.admin.form import list_supabase_users

        client = create_client(url, service_key)
        users = list_supabase_users(client=client)
        user_id = next(
            (uid for uid, email in users if email.lower() == admin_email),
            None,
        )
        if not user_id:
            app.logger.info(
                "ADMIN_EMAIL=%s not yet registered; skipping admin promotion",
                admin_email,
            )
            return

        # Anyone can sign up with any address. Promote only once the address
        # is confirmed (meaningful because auto-confirm was ruled out above).
        auth_user = client.auth.admin.get_user_by_id(user_id).user
        if not getattr(auth_user, "email_confirmed_at", None):
            app.logger.warning(
                "ADMIN_EMAIL=%s is registered but not confirmed; "
                "skipping admin promotion",
                admin_email,
            )
            return

        conn = psycopg2.connect(
            host=app.config["POSTGRES_HOST"],
            port=app.config["POSTGRES_PORT"],
            user=app.config["POSTGRES_USER"],
            password=app.config["POSTGRES_PASSWORD"],
            database=app.config["POSTGRES_DB_NAME"],
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO _fd.user_roles (user_id, role, assigned_by) "
                    "VALUES (%s, 'admin', %s) "
                    "ON CONFLICT (user_id) DO UPDATE "
                    "SET role = EXCLUDED.role, assigned_at = now() "
                    "WHERE _fd.user_roles.role <> 'admin'",
                    (user_id, user_id),
                )
                cur.execute(
                    "INSERT INTO _fd.role_audit "
                    "(user_id, old_role, new_role, changed_by) "
                    "SELECT %s, NULL, 'admin', %s "
                    "WHERE NOT EXISTS (SELECT 1 FROM _fd.role_audit "
                    "                  WHERE user_id = %s AND new_role = 'admin')",
                    (user_id, user_id, user_id),
                )
            conn.commit()
            app.logger.info("Promoted %s to admin", admin_email)
        finally:
            conn.close()
    except Exception as exc:
        app.logger.warning("Admin bootstrap failed: %s", exc)


def _apply_schema(app, order=None):
    """Idempotently apply the core SQL schema files at boot.

    Every file is written with ``CREATE ... IF NOT EXISTS`` / ``ADD COLUMN
    IF NOT EXISTS`` so re-running is safe. Each file runs in its own
    transaction; a failure is logged and skipped so one bad/optional file
    cannot block Flask boot.

    Plugin schema (PBPK, horizontal FL, …) and kernel schema are applied
    separately by the plugin loader (``apply_plugin_schema``). The PBPK and FL
    modules are now plugins, so ``pbpk_schema.sql`` / ``fl_schema.sql`` are no
    longer applied here — and migrate_schema.sql no longer needs a second pass
    (its plugin-dependent tail ALTERs moved into the owning plugin/kernel SQL).
    """
    base = os.path.dirname(os.path.abspath(__file__))
    order = order or [
        "migrate_schema.sql",
        "rbac_schema.sql",
        "demo_schema.sql",
    ]
    try:
        conn = psycopg2.connect(
            host=app.config["POSTGRES_HOST"],
            port=app.config["POSTGRES_PORT"],
            user=app.config["POSTGRES_USER"],
            password=app.config["POSTGRES_PASSWORD"],
            database=app.config["POSTGRES_DB_NAME"],
        )
    except Exception as exc:
        app.logger.warning("Schema apply skipped (no DB connection): %s", exc)
        return
    try:
        for fname in order:
            path = os.path.join(base, fname)
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    sql_text = fh.read()
                with conn.cursor() as cur:
                    cur.execute(sql_text)
                conn.commit()
                app.logger.info("Applied schema file: %s", fname)
            except Exception as exc:
                conn.rollback()
                app.logger.warning("Schema file %s failed: %s", fname, exc)
    finally:
        conn.close()


def create_app(db_name=None):
    """Construct the core application of Flask. Holds an
    optional argument to override the databse URI, this is used
    for Pytest."""
    _base = os.path.dirname(os.path.abspath(__file__))
    app = Flask(
        __name__,
        template_folder=os.path.join(_base, "../frontend/templates"),
        static_folder=os.path.join(_base, "../static"),
    )
    app.config.from_object(Config)
    require_strong_secret_key(app)
    # Believe X-Forwarded-* only from the configured number of reverse
    # proxies. Trusting it while Flask is reachable directly would let any
    # client pick its own IP and slip past the per-IP rate limits.
    n_proxies = app.config.get("TRUSTED_PROXY_COUNT", 0)
    if n_proxies > 0:
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=n_proxies, x_proto=n_proxies, x_host=n_proxies
        )
    if db_name is not None:
        app.config["POSTGRES_DB_NAME"] = db_name

    app.register_blueprint(main_routes, url_prefix="/")
    app.register_blueprint(auth_routes, url_prefix="/auth")
    app.register_blueprint(dashboard_routes, url_prefix="/dashboard")
    app.register_blueprint(data_routes, url_prefix="/data")
    app.register_blueprint(privacy_routes, url_prefix="/privacy")
    app.register_blueprint(visualization_routes, url_prefix="/visualization")
    app.register_blueprint(admin_routes, url_prefix="/admin")
    app.register_blueprint(demo_routes, url_prefix="/api/demo")

    # Plugin discovery + blueprint/template mounting. Runs alongside the
    # hardcoded registrations above; a no-op until plugins land under
    # backend/plugins/ (migration plan Phase 2). DB schema + bucket creation
    # for plugins is deferred to the boot block below.
    plugins = discover_plugins(app)
    register_plugins(app, plugins)

    # Single CORS init — flask-cors must only be applied once per app, or it
    # registers multiple after_request handlers and emits duplicated /
    # conflicting Access-Control-Allow-Origin headers. Per-resource rules:
    #   /api/demo/*  → public portal origin, GET only, no credentials
    #   everything   → (development only) localhost:5000 with credentials
    portal_origin = app.config.get("PORTAL_ORIGIN", "http://localhost:3000")
    cors_resources = {
        r"/api/demo/*": {
            "origins": portal_origin,
            "methods": ["GET"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": False,
        }
    }
    if app.config["ENV"] == "development":
        cors_resources[r"/*"] = {
            "origins": "http://localhost:5000",
            "supports_credentials": True,
        }
    CORS(app, resources=cors_resources)

    if app.config["ENV"] != "testing":
        limiter.init_app(app)

    supabase_extension.init_app(app)

    if app.config.get("ENV") != "testing":
        _apply_schema(app)  # before _bootstrap_admin: it needs _fd.user_roles
        # Kernel SQL + each plugin's migrations. After _apply_schema so the
        # _fd schema exists; idempotent.
        apply_plugin_schema(app, plugins)
        # Last, so it also covers kernel + plugin tables: take back the
        # blanket _fd grants and switch row rules on everywhere.
        _apply_schema(app, ["fd_lockdown.sql"])
        _bootstrap_admin(app)
        bootstrap_plugin_buckets(app, plugins)

    app.teardown_appcontext(teardown_db)
    init_csrf(app)

    @app.before_request
    def before_request():
        """Establish the database connection for the current request."""
        g.db = get_db()

    @app.context_processor
    def inject_role():
        role = getattr(g, "role", None)
        return {
            "current_role": role,
            "is_admin": role == "admin",
            "is_curator": role == "curator",
            "can_upload": role in ("admin", "curator"),
            "current_path": request.path if request else "",
        }

    @app.errorhandler(GenericExceptionHandler)
    def handle_generic_exception(e):
        if hasattr(e, "redirect_to") and e.redirect_to:
            flash(e.message, "danger")
            return redirect(url_for(e.redirect_to))
        return json.jsonify(e.to_dict()), e.status_code

    return app


if __name__ == "__main__":
    app = create_app()
    load_settings(app)
    # threaded=True so a plugin can make an in-process HTTP call to another
    # plugin's route (e.g. horizontal_fl → POST /model/parameter-sets) without
    # the single-threaded dev server deadlocking on the self-request.
    # The interactive debugger runs arbitrary Python from the browser, so it
    # is opt-in (FLASK_DEBUG=1) and never on by default.
    debug = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true")
    app.run(debug=debug, threaded=True)
