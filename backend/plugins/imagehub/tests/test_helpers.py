"""Pure helper tests. Synthetic values only."""
import copy
import datetime
import re

import pytest

from plugins.imagehub import config, ingest
from plugins.imagehub.helpers import (
    annotator_label,
    browser_url,
    display_rows,
    dedupe_headers,
    experiment_key,
    experiment_tokens,
    export_value,
    format_minutes,
    image_filter,
    image_order,
    image_status,
    legend_descriptions,
    mime_type,
    parse_via,
    region_to_svg,
    storage_key,
    to_text,
    treatment_flags,
)
from plugins.imagehub.rules import apply_steps
from plugins.imagehub.tests import leaf, synthetic

EXAMPLE = synthetic.dataset()


def test_treatment_flags_do_not_merge_but_report():
    flags = treatment_flags({"abt-199", "abt199", "a+b", "plain"})
    assert "abt199" in flags["abt-199"] and "abt-199" in flags["abt199"]
    assert "combination" in flags["a+b"]
    assert "plain" not in flags


def test_dedupe_headers_keeps_both_and_names_blanks():
    assert dedupe_headers(["a", "a", None, "T donor  ", "a"]) == [
        "a", "a_2", "(no header, column 3)", "T donor  ", "a_3",
    ]


@pytest.mark.parametrize("value,expected", [
    (2832, "2832"), (2832.0, "2832"), (0.5, "0.5"), ("  ", None), (None, None),
    ("rituximab ", "rituximab "),
    (datetime.date(2024, 1, 2), "2024-01-02"),
])
def test_to_text(value, expected):
    assert to_text(value) == expected


def test_experiment_key_ignores_the_pattern_and_punctuation():
    ignore = EXAMPLE.names_ignore_re
    assert experiment_key("20230622 Drug screen 2 (AA)", ignore) == experiment_key(
        "20230622 drug-screen 2", ignore
    )
    assert experiment_key("Screen (AA)") != experiment_key("Screen")
    assert experiment_key("Screen (AB)", re.compile(r"\(AB\)")) == "screen"


def test_experiment_tokens():
    tokens = EXAMPLE.tokens_re
    assert experiment_tokens("20240927_EXP36_T-cells", tokens) == {"EXP36"}
    assert experiment_tokens("bd991 one vid", tokens) == {"BD991"}
    # Only whole codes: EXP36 inside a longer word is not one.
    assert experiment_tokens("XEXP36 and EXP4b", tokens) == set()


def test_storage_key_starts_with_the_dataset_and_has_only_allowed_characters():
    key = storage_key("spheroid_example", "20240103_EXP1_Screen [1]", "abc", "VID1 x.jpg")
    assert key == "spheroid_example/20240103_EXP1_Screen_1_/abc_VID1_x.jpg"
    assert storage_key("leaf_discs", None, "abc", "a.jpg") == "leaf_discs/unknown/abc_a.jpg"


def test_browser_url_replaces_host_and_adds_key():
    url = browser_url(
        "http://kong:8000/storage/v1/object/sign/b/k.jpg?token=t", "http://localhost:8000", "anon",
    )
    assert url == "http://localhost:8000/storage/v1/object/sign/b/k.jpg?token=t&apikey=anon"
    assert browser_url(None, "http://x", "anon") is None


def test_parse_via_layouts():
    region = {"shape_attributes": {"name": "ellipse"}, "region_attributes": {}}
    flat = {"a.jpg1": {"filename": "a.jpg", "size": 1, "regions": [region]}}
    project = {"_via_settings": {}, "_via_img_metadata": flat}
    old = {"a.jpg1": {"filename": "a.jpg", "size": 1, "regions": {"0": region}}}
    for data in (flat, project, old):
        assert parse_via(data) == [{"filename": "a.jpg", "size": 1, "regions": [region]}]


def test_mime_type():
    assert mime_type("a.TIF") == "image/tiff"
    assert mime_type("a.jpg") == "image/jpeg"
    assert mime_type("a.fcs") is None


@pytest.mark.parametrize("member,label", [
    ("x/set_inh_AA.json", "AA"),
    ("x/set_BB.json", "BB"),
    ("x/set.json", "unknown"),
    ("x/via_region_data (1).json", "unknown"),
    ("x/a_XY.json", "unknown"),
    ("x_AA/a.json", "unknown"),
])
def test_annotator_label(member, label):
    assert annotator_label(member, EXAMPLE.annotator_re) == label


def test_annotator_label_without_a_pattern_or_with_another_unknown():
    assert annotator_label("x/set_AA.json", None) == "unknown"
    assert annotator_label("x/set.json", EXAMPLE.annotator_re, "nobody") == "nobody"


@pytest.mark.parametrize("shape,tag,attrs", [
    ({"name": "ellipse", "cx": 10, "cy": 20, "rx": 3, "ry": 4},
     "ellipse", {"cx": 10.0, "cy": 20.0, "rx": 3.0, "ry": 4.0}),
    ({"name": "polygon", "all_points_x": [1, 2], "all_points_y": [3, 4]},
     "polygon", {"points": "1.0,3.0 2.0,4.0"}),
    ({"name": "circle", "cx": 1, "cy": 2, "r": 3}, "circle", {"cx": 1.0, "cy": 2.0, "r": 3.0}),
    ({"name": "rect", "x": 1, "y": 2, "width": 3, "height": 4},
     "rect", {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0}),
])
def test_region_to_svg(shape, tag, attrs):
    assert region_to_svg({"shape_attributes": shape}) == (tag, attrs)


def test_region_to_svg_rotated_ellipse_in_degrees():
    shape = {"name": "ellipse", "cx": 1, "cy": 2, "rx": 3, "ry": 4, "theta": 3.141592653589793}
    assert region_to_svg({"shape_attributes": shape})[1]["transform"] == "rotate(180.0 1.0 2.0)"


@pytest.mark.parametrize("shape", [
    {"name": "blob"},
    {"name": "ellipse", "cx": 1},
    {"name": "ellipse", "cx": "x", "cy": 2, "rx": 3, "ry": 4},
    {},
])
def test_region_to_svg_refuses_bad_shapes(shape):
    assert region_to_svg({"shape_attributes": shape}) is None


def test_image_status():
    assert image_status("b/k", False) == "in bucket"
    assert image_status(None, True) == "on disk only"
    assert image_status(None, False) == "disk not connected"


def _filter(args):
    return image_filter(args, EXAMPLE)


def test_image_filter_binds_values_and_converts_days():
    clauses, params = _filter({
        "experiment": "E'; DROP TABLE x", "treatment": "ibrutinib", "from_day": "2",
        "to_day": "4.5", "annotated": "1", "in_bucket": "1", "tissue": "",
    })
    assert params[0] == "spheroid_example" and clauses[0] == "i.dataset = %s"
    assert "E'; DROP TABLE x" in params
    assert not any("DROP" in c for c in clauses)
    # A list field is matched on one of its values, by containment.
    assert '{"treatment_norm": ["ibrutinib"]}' in params
    assert params[-4:] == ["timepoint_minutes", 2880, "timepoint_minutes", 6480]
    assert len(clauses) == 7


def test_image_filter_ignores_blank_and_bad_days():
    assert _filter({}) == (["i.dataset = %s"], ["spheroid_example"])
    assert _filter({"from_day": "soon", "to_day": "inf"}) == (["i.dataset = %s"], ["spheroid_example"])


def test_image_filter_text_is_stripped_and_unknown_params_are_ignored():
    clauses, params = _filter({"concentration": " 10 ", "vid": "1", "dataset": "other"})
    assert params == ["spheroid_example", '{"concentration": "10"}'] and len(clauses) == 2


def test_format_minutes():
    assert format_minutes(5048) == "3d 12h 8m"
    assert format_minutes(0) == "0d 0h 0m"
    assert format_minutes(None) == ""


def test_image_filter_channel_and_min_regions():
    clauses, params = _filter({"channel": "BF", "min_regions": "3"})
    assert params == ["spheroid_example", '{"channel": "BF"}', 3] and len(clauses) == 3
    assert _filter({"channel_norm": "PC"})[1][1:] == ['{"channel_norm": "PC"}']
    assert _filter({"min_regions": "many"})[1] == ["spheroid_example"]
    # 0 is a real value: at least one annotation, possibly without regions.
    assert _filter({"min_regions": "0"})[1][1:] == [0]


def test_export_value_shortens_only_midnight_dates():
    assert export_value("2023-01-05T00:00:00") == "2023-01-05"
    assert export_value("2023-01-05T10:30:00") == "2023-01-05T10:30:00"
    assert export_value(5) == 5


def test_legend_descriptions_skip_ditto_marks():
    rows = [["Sex", '"'], ["Age", None], ["WBC (G/L)", "White blood cell count"], ["x"]]
    assert legend_descriptions(rows) == {"wbc(g/l)": "White blood cell count"}


def test_display_rows_join_lists_add_units_and_skip_empty_optional_rows():
    record = {"group": "Exp", "image": {"vid": "1", "well": "A1", "timepoint_minutes": 1500},
              "sample": {"treatment_norm": ["a", "b"], "treatment_raw": "A;B",
                         "concentration": "10", "concentration_unit": "nM"}}
    rows = display_rows(EXAMPLE.ui["image_details"] + EXAMPLE.ui["sample_details"], record)
    shown = {r["label"]: (r["text"], r["raw"]) for r in rows}
    assert shown["VID / well / field"] == ("1 / A1 / ", "")
    assert shown["Time"] == ("1d 1h 0m", "")
    assert shown["Treatment"] == ("a + b", "A;B")
    assert shown["Concentration"] == ("10 nM", "")
    assert "Channel / raw" not in shown and "Variant" not in shown
    # Without a sample row every sample value is empty, not an error.
    assert display_rows(EXAMPLE.ui["sample_details"], {"sample": {}})[0]["text"] == ""


def test_image_order_binds_field_names():
    order, params = image_order(EXAMPLE)
    assert order == "i.experiment, i.fields -> %s, i.fields -> %s, i.fields -> %s, i.source_member"
    assert params == ["vid", "well", "timepoint_minutes"]



def test_disk_root_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("IMAGEHUB_DISK_ROOT", raising=False)
    assert ingest.disk_root_from_env() == "/mnt/d"
    monkeypatch.setenv("IMAGEHUB_DISK_ROOT", "  ")
    assert ingest.disk_root_from_env() == "/mnt/d"
    monkeypatch.setenv("IMAGEHUB_DISK_ROOT", "/data/microscope")
    assert ingest.disk_root_from_env() == "/data/microscope"


# ── extra image fields ─────────────────────────────────────────────────────────

def _leaf_with_extra():
    raw = copy.deepcopy(leaf.dataset().raw)
    raw["images"]["extra_fields"] = {
        "disc_area": {"type": "float", "unit": "mm2", "decimals": 1},
        "lesions": {"type": "int"},
    }
    raw["ui"]["filters"] += [
        {"field": "image.disc_area", "type": "range", "params": ["area_from", "area_to"]},
        {"param": "area", "field": "image.disc_area", "type": "select"},
        {"param": "lesions", "field": "image.lesions", "type": "select"},
    ]
    return config.Dataset(raw, "leaf with extra")


def test_float_range_keeps_decimals_and_int_range_stays_whole():
    ds = _leaf_with_extra()
    _, params = image_filter({"area_from": "1.25", "area_to": "2", "from_day": "1.5"}, ds)
    assert params[-4:] == ["disc_area", 1.25, "disc_area", 2.0]
    assert isinstance(params[-1], float)
    assert 2160 in params and isinstance(params[params.index(2160)], int)


def test_float_range_ignores_values_that_are_not_finite():
    ds = _leaf_with_extra()
    clauses, params = image_filter({"area_from": "inf", "area_to": "nan"}, ds)
    assert "disc_area" not in params and len(clauses) == 1


def test_select_on_extra_fields_uses_the_declared_type():
    ds = _leaf_with_extra()
    _, params = image_filter({"area": "2.50", "lesions": "3"}, ds)
    assert '{"disc_area": 2.5}' in params and '{"lesions": 3}' in params
    clauses, _ = image_filter({"area": "a lot"}, ds)
    assert "false" in clauses


def test_extra_fields_show_rounded_with_their_unit_on_pages_only():
    ds = _leaf_with_extra()
    specs = [{"label": "Area", "field": "image.disc_area"},
             {"label": "Lesions", "field": "image.lesions"},
             {"label": "Area, own unit", "field": "image.disc_area", "unit": "sample.unit"},
             {"label": "Missing", "field": "image.disc_area", "optional": True}]
    record = {"image": {"disc_area": 1234.567, "lesions": 3}, "sample": {"unit": "cm2"}}
    shown = {r["label"]: r["text"] for r in display_rows(specs, record, ds.extra_fields)}
    assert shown == {"Area": "1234.6 mm2", "Lesions": "3",
                     "Area, own unit": "1234.6 cm2", "Missing": "1234.6 mm2"}
    # Without the extra field specs (as before): the stored value, unrounded.
    assert display_rows(specs[:1], record)[0]["text"] == "1234.567"
    # No value: no unit either, and an optional row is left out.
    empty = display_rows(specs, {"image": {}, "sample": {}}, ds.extra_fields)
    assert [r["text"] for r in empty] == ["", "", ""]
