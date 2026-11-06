"""Image hub plugin manifest.

Catalogs imaging experiments, one config file per dataset: sample rows from the
lab's workbooks, images that live inside zip files on an external disk (uploaded
to the bucket only on selection) and VIA annotations.
"""
from kernel.plugin import Plugin

from .routes import routes

PLUGIN = Plugin(
    name="imagehub",
    version="0.1.0",
    url_prefix="/imagehub",
    blueprint=routes,

    sql_migrations=["sql/001_schema.sql", "sql/002_query_role.sql", "sql/003_dataset.sql"],

    # Import names; pip names are in requirements.txt (Pillow imports as PIL,
    # PyYAML as yaml).
    required_packages=["openpyxl", "PIL", "yaml"],

    storage_buckets=[{
        "id": "imagehub-images",
        "public": False,
        "size_limit": 50 * 1024 * 1024,    # 50 MB
        # JSON: the original VIA files, next to the images they annotate.
        "mime_whitelist": {"image/jpeg", "image/png", "image/tiff", "application/json"},
    }],

    # Anon key, needed for browser URLs: the gateway wants an API key on storage.
    # The second is the password of the read-only role used by query.py.
    required_env=["SUPABASE_KEY", "IMAGEHUB_RO_PASSWORD"],

    # admin/curator upload and delete, accessor queries. visualizer gets 403.
    roles_required=("admin", "curator", "accessor"),

    templates_dir="templates",
    nav={"label": "Image hub", "icon": "microscope"},
)
