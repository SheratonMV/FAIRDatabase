"""Builds dashboard.html: one self-contained file, for the export zip.

The page reads the same columns as metadata.csv, so a dashboard made here and one
filled by hand through "Open file" show the same thing. Thumbnails and annotation
shapes exist only in the one made here.
"""
import base64
import csv
import io
import json
import os

from PIL import Image, UnidentifiedImageError

from .helpers import region_to_svg

_ASSETS = os.path.join(os.path.dirname(__file__), "dashboard_assets")
MAX_BYTES = 20 * 1024 * 1024
THUMBNAIL_SIZE = 256
_THUMBNAIL_QUALITY = 70


def make_thumbnail(content):
    """``{"src", "w", "h"}`` with the original size in w and h, or None.

    w and h are what annotation coordinates refer to. Only 8-bit images: other
    pixel formats would need a contrast choice that should not be made silently.
    """
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.mode not in ("L", "RGB"):
                return None
            width, height = image.size
            image.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=_THUMBNAIL_QUALITY)
    except (UnidentifiedImageError, OSError):
        return None
    data = base64.b64encode(out.getvalue()).decode("ascii")
    return {"src": f"data:image/jpeg;base64,{data}", "w": width, "h": height}


def _annotation_shapes(annotations):
    """``[{"label", "regions"}]`` -> the shapes the page draws."""
    return [
        {
            "label": a["label"],
            "shapes": [s for s in (region_to_svg(r) for r in a["regions"]) if s],
        }
        for a in annotations
    ]


def _render(payload):
    with open(os.path.join(_ASSETS, "template.html"), encoding="utf-8") as fh:
        page = fh.read()
    with open(os.path.join(_ASSETS, "xlsx.full.min.js"), encoding="utf-8") as fh:
        library = fh.read()
    # Same JSON text, but sheet text cannot end the script block.
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\u0021--")
    page = page.replace("/*__SHEETJS__*/", library, 1)
    return page.replace("__IMAGEHUB_DATA__", data, 1)


def build_dashboard(metadata_csv, thumbnails, annotations, wells_without_images, info, layout=None):
    """Returns ``(html text, note or None)``.

    ``layout`` is the dataset's dashboard section (see ``export.dashboard_layout``):
    which columns name a sample row, the default groups and so on. Without it the
    page treats every row as its own sample.

    ``thumbnails`` and ``annotations`` are keyed by image path in the zip. If the
    file would pass MAX_BYTES, the thumbnails are dropped and the note says so.
    """
    reader = csv.reader(io.StringIO(metadata_csv))
    columns = next(reader)
    payload = {
        "columns": columns,
        "rows": list(reader),
        "images": thumbnails,
        "annotations": {key: _annotation_shapes(value) for key, value in annotations.items()},
        "wells_without_images": wells_without_images,
        "info": info,
        "name": info.get("name", ""),
        "layout": layout or {},
    }
    html = _render(payload)
    note = None
    if len(html.encode("utf-8")) > MAX_BYTES:
        note = (
            f"Thumbnails left out: with them, dashboard.html would pass "
            f"{MAX_BYTES // (1024 * 1024)} MB. Narrow the selection to include them."
        )
        html = _render({**payload, "images": {}, "info": {**info, "thumbnails": note}})
    return html, note
