"""Plugin loader — discovery, schema, buckets, mounting.

Core calls these from the Flask app factory. The loader is **additive**: with
no ``plugins/`` directory (or an empty one) every function is a safe no-op, so
it can ship before any plugin exists (migration plan Phase 2).

Pipeline, per the migration plan:

  1. ``discover_plugins()``        — scan ``plugins/*/plugin.py`` for ``PLUGIN``
  2. ``register_plugins(app, …)``  — mount blueprints + plugin template dirs
  3. ``apply_plugin_schema(app,…)``— apply kernel SQL + each plugin's migrations
  4. ``bootstrap_plugin_buckets`` — create declared Supabase Storage buckets

Steps 1–2 run unconditionally during app construction; steps 3–4 are gated to
non-testing boots (they need a live DB / Supabase), mirroring core's
``_apply_schema`` / ``_bootstrap_pbpk_bucket``.

Enforced boundaries (guide §3):
  * Two plugins cannot claim the same ``url_prefix`` — the second is dropped.
  * Every ``CREATE/ALTER TABLE _fd.X`` in a plugin's SQL must have ``X`` start
    with the manifest's ``table_prefix`` — violators are refused at boot.
  * ``current_plugin_name`` is set on every plugin-blueprint request via a
    ``before_request`` hook, so ``kernel.storage`` can scope bucket access.
  * Buckets are registered with their ``mime_whitelist`` so ``kernel.storage``
    can reject mismatched uploads.

``required_env`` policy: a plugin whose declared env var is unset is mounted
anyway with a logged warning; downstream HTTP errors at first call surface the
misconfiguration. We do NOT skip-mount, because most plugins have routes that
work fine without their optional env (e.g. a UI route doesn't need the API
key its export route does). Promote to a hard failure only if every route in
the plugin truly requires the env.
"""
import importlib
import importlib.util
import os
import re

import jinja2
import psycopg2
from supabase import create_client

from kernel import storage as _storage  # for bucket/contextvar wiring
from kernel.context import set_current_plugin

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__)).rsplit(os.sep, 1)[0]
PLUGINS_DIR = os.path.join(_BACKEND_DIR, "plugins")
KERNEL_SQL_DIR = os.path.join(_BACKEND_DIR, "kernel", "sql")


class LoadedPlugin:
    """A discovered plugin: its manifest plus the directory it lives in."""

    __slots__ = ("manifest", "dir")

    def __init__(self, manifest, directory):
        self.manifest = manifest
        self.dir = directory


# ── helpers ───────────────────────────────────────────────────────────────────

def _plugin_selection():
    """Read the plugin allow/deny lists from the environment.

    ``FAIRDB_PLUGINS`` — comma-separated allowlist. When set (and non-empty),
    ONLY the named plugins are loaded. Unset/empty → load all (back-compat).
    ``FAIRDB_PLUGINS_DISABLED`` — comma-separated denylist, applied after the
    allowlist. Names are plugin *folder* names (e.g. ``pbpk``).

    Returns ``(allow, deny)`` where ``allow`` is a set or ``None`` (no
    allowlist) and ``deny`` is a set (possibly empty).
    """
    def _parse(var):
        raw = os.getenv(var, "")
        return {p.strip() for p in raw.split(",") if p.strip()}

    allow = _parse("FAIRDB_PLUGINS")
    deny = _parse("FAIRDB_PLUGINS_DISABLED")
    return (allow or None), deny


def _missing_packages(names):
    """Return the subset of ``names`` (import module names) that are not
    importable in the current interpreter. Uses ``find_spec`` so no module is
    actually imported (cheap, no side effects)."""
    missing = []
    for name in names or ():
        # find_spec accepts dotted names; top-level is enough for our use.
        try:
            if importlib.util.find_spec(name) is None:
                missing.append(name)
        except (ImportError, ValueError):
            missing.append(name)
    return missing


def _normalize_nav(nav, url_prefix):
    """Resolve a plugin's nav entry into the dict the layout template renders.

    The sidebar carries one flat link per plugin (convention: sub-pages live
    inside the plugin via in-page tabs, not in the global sidebar). The link
    target is ``nav["path"]`` joined onto ``url_prefix`` (or used absolute if
    it starts with ``/``); when ``path`` is omitted it defaults to the plugin's
    landing page ``<url_prefix>/ui``. Unknown keys pass through so future
    fields (badge, role gate, ...) don't need a loader change.
    """
    path = nav.get("path", "ui")
    if path.startswith("/"):
        href = path
    else:
        href = url_prefix.rstrip("/") + "/" + path.lstrip("/")
    return {**nav, "url_prefix": url_prefix, "href": href}


# ── 1. Discovery ──────────────────────────────────────────────────────────────

def discover_plugins(app=None):
    """Scan ``plugins/*/plugin.py`` and return a list of ``LoadedPlugin``.

    Each plugin folder must expose a module-level ``PLUGIN`` (a
    ``kernel.plugin.Plugin``). A folder that fails to import or lacks ``PLUGIN``
    is logged and skipped — one bad plugin cannot block boot.
    """
    log = app.logger if app else None
    found = []
    if not os.path.isdir(PLUGINS_DIR):
        return found

    allow, deny = _plugin_selection()

    for name in sorted(os.listdir(PLUGINS_DIR)):
        pdir = os.path.join(PLUGINS_DIR, name)
        if name.startswith((".", "_")) or not os.path.isdir(pdir):
            continue
        if not os.path.exists(os.path.join(pdir, "plugin.py")):
            continue
        if allow is not None and name not in allow:
            if log:
                log.info("Plugin %r not in FAIRDB_PLUGINS allowlist; skipping", name)
            continue
        if name in deny:
            if log:
                log.info("Plugin %r in FAIRDB_PLUGINS_DISABLED; skipping", name)
            continue
        try:
            module = importlib.import_module(f"plugins.{name}.plugin")
            manifest = getattr(module, "PLUGIN", None)
            if manifest is None:
                raise AttributeError("module defines no PLUGIN")
            found.append(LoadedPlugin(manifest, pdir))
            if log:
                log.info("Discovered plugin %r v%s", manifest.name, manifest.version)
        except Exception as exc:  # noqa: BLE001
            if log:
                log.warning("Plugin %r failed to load: %s", name, exc)

    return found


# ── 2. Blueprints + templates ─────────────────────────────────────────────────

def register_plugins(app, plugins):
    """Mount each plugin's blueprint at its ``url_prefix`` and add its template
    directory to the Jinja search path.

    Plugin template dirs are appended *after* core's loader, so a plugin can
    never shadow a core template. Two plugins claiming the same ``url_prefix``
    is rejected — the second is logged and skipped, since silent overwrite would
    break the first plugin invisibly.

    Also: every plugin blueprint gets a ``before_request`` hook that stamps
    the plugin name onto the request via ``set_current_plugin``. That's what
    ``kernel.storage`` reads to scope bucket access per guide §3.

    Buckets declared in each manifest are registered with ``kernel.storage``
    so the helper can enforce ``mime_whitelist`` at upload time.
    """
    extra_loaders = []
    nav = []
    seen_prefix = {}
    for lp in plugins:
        m = lp.manifest
        existing = seen_prefix.get(m.url_prefix)
        if existing:
            app.logger.warning(
                "Plugin %r url_prefix %s collides with %r; skipping the second",
                m.name, m.url_prefix, existing,
            )
            continue
        missing = _missing_packages(m.required_packages)
        if missing:
            app.logger.warning(
                "Plugin %r skip-mounted: missing required_packages %s. "
                "Install via plugins/%s/requirements.txt.",
                m.name, missing, m.name,
            )
            continue
        try:
            _attach_plugin_hooks(m)
            app.register_blueprint(m.blueprint, url_prefix=m.url_prefix)
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("Plugin %r blueprint mount failed: %s", m.name, exc)
            continue
        seen_prefix[m.url_prefix] = m.name

        for bucket in m.storage_buckets:
            _storage.register_bucket(m.name, bucket)

        if m.templates_dir:
            tdir = os.path.join(lp.dir, m.templates_dir)
            if os.path.isdir(tdir):
                extra_loaders.append(jinja2.FileSystemLoader(tdir))

        if m.nav:
            nav.append(_normalize_nav(m.nav, m.url_prefix))
        app.logger.info("Mounted plugin %r at %s", m.name, m.url_prefix)

    if extra_loaders:
        app.jinja_loader = jinja2.ChoiceLoader([app.jinja_loader, *extra_loaders])

    # Expose nav entries to the core layout template.
    app.config["PLUGIN_NAV"] = nav

    @app.context_processor
    def _inject_plugin_nav():
        return {"plugin_nav": app.config.get("PLUGIN_NAV", [])}


# ── per-plugin before_request hook ────────────────────────────────────────────

def _attach_plugin_hooks(manifest):
    """Wire ``before_request`` on the plugin blueprint so every request handled
    by it stamps the plugin name onto ``g`` for ``kernel.storage`` to read.

    ``manifest.blueprint`` is a module-level object, cached in ``sys.modules``
    across the whole process — so if ``register_plugins`` runs more than once
    in one process (multiple ``create_app()`` calls, e.g. the test suite's
    per-module ``app`` fixture), a second call here would re-decorate the
    *same* Blueprint with ``before_request``. Flask raises
    ``AssertionError``/setup-method errors on that once a blueprint has
    already been registered to any app, which ``register_plugins`` swallows —
    silently skipping the blueprint mount for every app after the first. Only
    attach the hook once per blueprint object; Flask replays it for every
    subsequent ``register_blueprint`` call regardless of when it was added.
    """
    if getattr(manifest.blueprint, "_fd_hook_attached", False):
        return
    name = manifest.name
    bp = manifest.blueprint
    bp._fd_hook_attached = True

    @bp.before_request
    def _stamp_plugin():
        set_current_plugin(name)


# ── SQL prefix guard ──────────────────────────────────────────────────────────

# Matches CREATE TABLE, ALTER TABLE, CREATE INDEX … ON _fd.<ident>. Tolerates
# optional IF NOT EXISTS / IF EXISTS / UNIQUE between the keyword and the
# identifier. Quoted identifiers are deliberately not allowed — plugins must
# use plain snake_case names.
_DDL_RE = re.compile(
    r"\b(?:CREATE\s+TABLE|ALTER\s+TABLE|CREATE(?:\s+UNIQUE)?\s+INDEX[^;]*?\bON)"
    r"(?:\s+IF\s+(?:NOT\s+)?EXISTS)?\s+_fd\.([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)


def _violates_table_prefix(sql_text, table_prefix):
    """Return the first ``_fd.<ident>`` referenced by a DDL statement in
    ``sql_text`` whose ident does NOT start with ``table_prefix``, or ``None``."""
    for match in _DDL_RE.finditer(sql_text):
        ident = match.group(1)
        if not ident.startswith(table_prefix):
            return ident
    return None


# ── shared SQL apply ──────────────────────────────────────────────────────────

def _connect(app):
    return psycopg2.connect(
        host=app.config["POSTGRES_HOST"],
        port=app.config["POSTGRES_PORT"],
        user=app.config["POSTGRES_USER"],
        password=app.config["POSTGRES_PASSWORD"],
        database=app.config["POSTGRES_DB_NAME"],
    )


def _apply_sql_files(app, conn, paths, *, table_prefix=None):
    """Apply each SQL file in its own transaction; log+skip on failure.

    Mirrors core's ``_apply_schema``: every plugin migration is expected to be
    idempotent (``CREATE … IF NOT EXISTS``), so a failure of one file cannot
    block boot.

    When ``table_prefix`` is set, refuses to apply any file that contains a
    ``CREATE/ALTER TABLE _fd.<ident>`` (or ``CREATE INDEX … ON _fd.<ident>``)
    whose ident doesn't start with the prefix. This is the §3 table-prefix
    boundary, enforced at boot rather than left to code review.
    """
    for path in paths:
        if not os.path.exists(path):
            app.logger.warning("SQL file missing, skipped: %s", path)
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                sql_text = fh.read()
            if table_prefix is not None:
                bad = _violates_table_prefix(sql_text, table_prefix)
                if bad:
                    app.logger.error(
                        "SQL file %s creates _fd.%s outside table_prefix %r; "
                        "refusing to apply (PLUGIN_GUIDE.md §3)",
                        path, bad, table_prefix,
                    )
                    continue
            with conn.cursor() as cur:
                cur.execute(sql_text)
            conn.commit()
            app.logger.info("Applied SQL file: %s", path)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            app.logger.warning("SQL file %s failed: %s", path, exc)


# ── 3. Schema ─────────────────────────────────────────────────────────────────

def apply_plugin_schema(app, plugins):
    """Apply the kernel's own SQL, then every plugin's ``sql_migrations``.

    Kernel SQL (``kernel/sql/*.sql``) runs first and unconditionally — it backs
    ``kernel.audit`` and is needed even when no plugin is installed.
    """
    try:
        conn = _connect(app)
    except Exception as exc:  # noqa: BLE001
        app.logger.warning("Plugin schema apply skipped (no DB connection): %s", exc)
        return

    try:
        kernel_sql = []
        if os.path.isdir(KERNEL_SQL_DIR):
            kernel_sql = [
                os.path.join(KERNEL_SQL_DIR, f)
                for f in sorted(os.listdir(KERNEL_SQL_DIR))
                if f.endswith(".sql")
            ]
        _apply_sql_files(app, conn, kernel_sql)

        for lp in plugins:
            paths = [
                os.path.join(lp.dir, rel) for rel in lp.manifest.sql_migrations
            ]
            _apply_sql_files(
                app, conn, paths, table_prefix=lp.manifest.table_prefix,
            )
    finally:
        conn.close()


# ── 4. Storage buckets ────────────────────────────────────────────────────────

def bootstrap_plugin_buckets(app, plugins):
    """Create every Supabase Storage bucket declared in a plugin manifest.

    Idempotent: an "already exists" / 409 response is treated as success. Any
    other failure is logged and swallowed — a transient Supabase outage must
    not crash boot (mirrors core's ``_bootstrap_pbpk_bucket``).
    """
    declared = [
        (lp.manifest.name, b)
        for lp in plugins
        for b in lp.manifest.storage_buckets
    ]
    if not declared:
        return

    url = app.config.get("SUPABASE_URL")
    service_key = app.config.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not service_key:
        app.logger.info("Supabase not configured; skipping plugin bucket bootstrap")
        return

    try:
        client = create_client(url, service_key)
    except Exception as exc:  # noqa: BLE001
        app.logger.warning("Plugin bucket bootstrap skipped: %s", exc)
        return

    for plugin_name, bucket in declared:
        bid = bucket.get("id")
        options = {"public": bool(bucket.get("public", False))}
        if bucket.get("size_limit") is not None:
            options["file_size_limit"] = bucket["size_limit"]
        try:
            client.storage.create_bucket(bid, options=options)
            app.logger.info("Created Storage bucket %r (plugin %r)", bid, plugin_name)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "already exists" in msg or "duplicate" in msg or "409" in msg:
                app.logger.info("Storage bucket %r already exists; skipping", bid)
            else:
                app.logger.warning("Bucket %r bootstrap failed: %s", bid, exc)


# ── orchestration ─────────────────────────────────────────────────────────────

def load_plugins(app, *, with_schema=True):
    """Run the full pipeline. Returns the discovered plugin list.

    ``with_schema=False`` (testing) skips DB schema + bucket creation but still
    discovers and mounts blueprints.
    """
    plugins = discover_plugins(app)
    register_plugins(app, plugins)

    for lp in plugins:
        for key in lp.manifest.required_env:
            if not os.getenv(key):
                app.logger.warning(
                    "Plugin %r requires env %r which is unset",
                    lp.manifest.name, key,
                )

    if with_schema:
        apply_plugin_schema(app, plugins)
        bootstrap_plugin_buckets(app, plugins)
    return plugins
