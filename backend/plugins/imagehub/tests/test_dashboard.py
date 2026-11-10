"""dashboard.py on synthetic data. The page's own logic: dashboard_smoke.js."""
import base64
import io
import json
import os
import re

from PIL import Image

from plugins.imagehub import dashboard, export
from plugins.imagehub.tests import synthetic
from plugins.imagehub.dashboard import build_dashboard, make_thumbnail

CSV = "image_file,well,regions_AA,Viability (%)\nimages/a.jpg,A1,3,80\n"
EXAMPLE = synthetic.dataset()
CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data: blob:"
)


def _embedded(html):
    text = re.search(r'id="embedded" type="application/json">(.*?)</script>', html, re.S).group(1)
    return json.loads(text)


def _jpeg(size=(1536, 1152), mode="RGB"):
    out = io.BytesIO()
    Image.new(mode, size, 128 if mode == "L" else (9, 9, 9)).save(out, "JPEG")
    return out.getvalue()


def test_thumbnail_is_small_and_keeps_the_original_size_for_the_overlay():
    thumbnail = make_thumbnail(_jpeg())
    assert (thumbnail["w"], thumbnail["h"]) == (1536, 1152)
    data = base64.b64decode(thumbnail["src"].split(",", 1)[1])
    assert Image.open(io.BytesIO(data)).size == (256, 192)


def test_thumbnail_refuses_other_pixel_formats_and_junk():
    out = io.BytesIO()
    Image.new("I;16", (4, 4)).save(out, "TIFF")
    assert make_thumbnail(out.getvalue()) is None
    assert make_thumbnail(b"nope") is None


def test_page_blocks_the_network_and_loads_nothing_external():
    html, note = build_dashboard(CSV, {}, {}, [], {})
    assert note is None and f'content="{CSP}"' in html
    template = open(f"{dashboard._ASSETS}/template.html", encoding="utf-8").read()
    assert not re.search(r"""(src|href)\s*=\s*["']?https?:""", template)
    assert not re.search(r"\b(fetch|XMLHttpRequest|WebSocket)\b", template.split('id="app"')[1])


def test_page_names_no_dataset_column():
    # Every column the page treats in a special way comes from the dataset's config.
    app = open(f"{dashboard._ASSETS}/template.html", encoding="utf-8").read().split('id="app"')[1]
    board = EXAMPLE.dashboard
    named = {*board["key"], *board["expected"], *board["values"], *board["colour_by"],
             *board["compare_by"], *board["time"], *board["channel"], *board["units"].values(),
             f"regions_{board['annotator']}"}
    # As a string or a row's key; a word in a sentence or a variable is fine.
    found = [n for n in sorted(named)
             if re.search(rf"""(["'`]){re.escape(n)}\1|\b(r|row|w)\.{re.escape(n)}\b""", app)]
    assert not found


def test_layout_for_the_smoke_test_matches_the_example_config():
    # dashboard_smoke.js reads this file, so the page is tested with the shipped config.
    layout = json.dumps(export.dashboard_layout(EXAMPLE), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    path = os.path.join(os.path.dirname(__file__), "golden", "dashboard_layout.golden")
    if os.getenv("IMAGEHUB_UPDATE_GOLDEN"):
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(layout)
    with open(path, encoding="utf-8", newline="") as fh:
        assert fh.read() == layout


def test_layout_is_in_the_payload():
    html, _ = build_dashboard(CSV, {}, {}, [], {}, export.dashboard_layout(EXAMPLE))
    layout = _embedded(html)["layout"]
    assert layout["key"] == ["experiment", "vid", "well"]
    assert layout["words"] == {"group": "experiment", "sample": "well"}
    assert _embedded(build_dashboard(CSV, {}, {}, [], {})[0])["layout"] == {}


def test_sheet_text_cannot_end_the_script_block():
    text = "</script><script>alert(1)</script><!-- x"
    html, _ = build_dashboard(f"a,b\n1,{text}\n", {}, {}, [], {})
    assert _embedded(html)["rows"] == [["1", text]]
    block = html.split('id="embedded" type="application/json">')[1].split("</script>")[0]
    assert "</" not in block and "<!--" not in block


def test_embedded_data_has_shapes_and_only_drawable_regions():
    regions = [
        {"shape_attributes": {"name": "ellipse", "cx": 1, "cy": 2, "rx": 3, "ry": 4}},
        {"shape_attributes": {"name": "blob"}},
    ]
    html, _ = build_dashboard(
        CSV, {"images/a.jpg": {"src": "data:x", "w": 8, "h": 6}},
        {"images/a.jpg": [{"label": "AA", "regions": regions}]},
        [{"experiment": "E", "vid": "1", "well": "B2"}], {"created": "now"},
    )
    data = _embedded(html)
    assert data["columns"][0] == "image_file" and data["images"]["images/a.jpg"]["w"] == 8
    assert data["annotations"]["images/a.jpg"] == [{
        "label": "AA", "shapes": [["ellipse", {"cx": 1.0, "cy": 2.0, "rx": 3.0, "ry": 4.0}]],
    }]
    assert data["wells_without_images"][0]["well"] == "B2"


def test_too_large_drops_thumbnails_and_says_so(monkeypatch):
    monkeypatch.setattr(dashboard, "MAX_BYTES", 2 * 1024 * 1024)
    big = {"images/a.jpg": {"src": "x" * (3 * 1024 * 1024), "w": 8, "h": 6}}
    html, note = build_dashboard(CSV, big, {}, [], {})
    data = _embedded(html)
    assert "left out" in note and data["images"] == {} and data["info"]["thumbnails"] == note
    assert len(html.encode()) < 2 * 1024 * 1024
