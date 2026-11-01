"""Plugins must mount on every Flask app built in the same process.

Each test fixture builds a fresh app, but plugin blueprints are module-level
objects shared by all of them. The loader used to add its per-plugin hook by
changing the blueprint itself, which Flask forbids once the blueprint has been
registered on any app, so every app after the first came up without its
plugin routes (and plugin tests failed with 404). These tests build two apps
and check that both mount the plugins and run the hook.
"""
from flask import Flask

from kernel import loader
from kernel.context import current_plugin


def _build_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    plugins = loader.discover_plugins(app)
    loader.register_plugins(app, plugins)
    return app, plugins


def _plugin_prefixes(plugins):
    return {lp.manifest.url_prefix for lp in plugins}


def _mounted_prefixes(app, prefixes):
    rules = [r.rule for r in app.url_map.iter_rules()]
    return {p for p in prefixes if any(rule.startswith(p + "/") or rule == p for rule in rules)}


def test_second_app_still_mounts_plugins(caplog):
    first, plugins = _build_app()
    prefixes = _plugin_prefixes(plugins)
    mounted_first = _mounted_prefixes(first, prefixes)

    caplog.clear()
    second, _ = _build_app()

    assert "blueprint mount failed" not in caplog.text
    assert _mounted_prefixes(second, prefixes) == mounted_first


def test_hook_stamps_plugin_name_on_every_app():
    for _ in range(2):
        app, plugins = _build_app()
        mounted = [lp.manifest for lp in plugins
                   if lp.manifest.blueprint.name in app.blueprints]
        assert mounted, "no plugin mounted; nothing to check"
        for m in mounted:
            hooks = app.before_request_funcs.get(m.blueprint.name, [])
            assert hooks, f"{m.name}: no before_request hook on this app"
            with app.test_request_context():
                for hook in hooks:
                    hook()
                assert current_plugin() == m.name
