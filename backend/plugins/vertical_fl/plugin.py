"""Plugin manifest."""
from kernel.plugin import Plugin

from .routes import routes

PLUGIN = Plugin(
    # `name` must be alphanumeric/underscore. It prefixes your tables
    # (`_fd.<name>_*`) and buckets (`<name>-*`).
    name="vertical_fl",
    version="0.1.0",
    url_prefix="/vfl",
    blueprint=routes,

    # Idempotent SQL, applied at boot. Paths are relative to this folder.
    sql_migrations=["sql/001_schema.sql"],

    table_prefix="vfl_",

    # Default role scope. Routes still declare their own @login_required(...);
    # this documents the plugin's intended audience and is checked by review.
    roles_required=("admin", "curator", "accessor", "visualizer"),

    # UI is served by the horizontal_fl plugin dashboard (/fl/ui, Vertical FL tab).
)
