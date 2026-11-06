"""rules.py: cleaning values with a config's steps. No database.

The spheroid cases run through the example config, so they test both the steps
and the way the example writes them.
"""
import pytest

from plugins.imagehub.config import Dataset
from plugins.imagehub.rules import apply_steps, parse_filename, value_mapping
from plugins.imagehub.tests import synthetic

EXAMPLE = synthetic.dataset()
DERIVED = EXAMPLE.metadata["derived"]


def _clean(field, raw):
    return apply_steps(raw, DERIVED[field]["steps"])


@pytest.mark.parametrize("raw,expected", [
    ("Ibrutinib", ["ibrutinib"]),
    ("rituximab ", ["rituximab"]),
    ("ABT-199;S-63845", ["venetoclax", "s-63845"]),
    ("ABT-199", ["venetoclax"]),
    ("Venetoclax", ["venetoclax"]),
    ("ABT-199;Venetoclax", ["venetoclax"]),
    ("a ; b;", ["a", "b"]),
    ("a;A", ["a"]),
    ("", []),
    (None, []),
])
def test_treatment(raw, expected):
    assert _clean("treatment_norm", raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("unstimulated ", ["unstimulated"]),
    ("Unstimulated", ["unstimulated"]),
    ("IL2/IL15/IL21/CpG", ["il-2/15/21/cpg"]),
    ("IL-2/15/21/CpG;aCD3/aCD28", ["il-2/15/21/cpg", "acd3/acd28"]),
    ("IL-2/15/21/CpG/aCD3/aCD28", ["il-2/15/21/cpg", "acd3/acd28"]),
    ("IL2/IL15/IL21/CpG/aCD3/aCD29", ["il-2/15/21/cpg", "acd3/acd29"]),
    ("aCD3/aCD39", ["acd3/acd39"]),
    ("3T40 overnight", ["3t40 overnight"]),
    (None, []),
])
def test_stimulation(raw, expected):
    assert _clean("stimulation_norm", raw) == expected


@pytest.mark.parametrize("vid,expected", [
    ("2832", ["2832"]),
    ("3494;3495", ["3494", "3495"]),
    ("418 midpoint", ["418 midpoint"]),
    ("BD99", ["BD99"]),
    (None, []),
])
def test_vids(vid, expected):
    assert _clean("vids", vid) == expected


def test_each_step_on_its_own():
    assert apply_steps(" A | b |a", [{"split": "|"}]) == [" A ", " b ", "a"]
    assert apply_steps([" A ", "b "], ["strip", "upper"]) == ["A", "B"]
    assert apply_steps(["x", "", "x", "y"], ["drop_empty", "dedupe"]) == ["x", "y"]
    assert apply_steps(["n", "N"], [{"synonyms": {"N": "nitrogen"}}]) == ["n", "nitrogen"]
    rule = {"canonical": "mix", "variants": ["mix", "m-i-x"], "separator": "+"}
    assert apply_steps(["m-i-x+salt", "mix", "mixer"], [{"split_off_prefix": rule}]) == ["mix", "salt", "mix", "", "mixer"]
    assert apply_steps("kept", []) == ["kept"]


def test_unknown_steps_are_refused():
    with pytest.raises(ValueError):
        apply_steps("x", ["shout"])
    with pytest.raises(ValueError):
        apply_steps("x", ["unsplit"])


def test_value_mapping_counts_rows_per_raw_value():
    rows = [{"t": "A;b"}, {"t": "A;b"}, {"t": None}]
    assert value_mapping(rows, "t", [{"split": ";"}, "lower"]) == {"A;b": (["a", "b"], 2), None: ([], 1)}


# ── file names ──

@pytest.mark.parametrize("name,fields", [
    ("VID3201_C3_1_03d12h08m.jpg",
     dict(vid="3201", well="C3", field=1, timepoint_minutes=5048, channel="jpg", variant=None)),
    ("BD99_B3_2_00d00h00m.jpg", dict(vid="BD99", well="B3", field=2, timepoint_minutes=0)),
    ("Phase_A1_1_00d01h00m.tif", dict(vid=None, well="A1", channel="Phase", timepoint_minutes=60)),
    ("VID1_Phase_A12_1_00d00h30m.tif", dict(vid="1", well="A12", channel="Phase")),
    ("VID1169_A2_1_04d00h00m_masks.tif", dict(vid="1169", well="A2", channel="tif", variant="masks")),
    ("VID1_A1_1_00d00h00m.JPEG", dict(channel="jpg")),
    ("VID1_A1_1_00d00h00m.tiff", dict(channel="tif")),
    ("VID1_A1_1_00d00h00m.png", dict(channel="png")),
    ("BF_A1_1_00d00h00m.tif", dict(channel="BF", timepoint_minutes=0)),
    ("VID2204_E9_1_04d00h00m_raw BF.tif", dict(variant="raw BF")),
])
def test_spheroid_names(name, fields):
    parsed = parse_filename(EXAMPLE, name)
    assert {k: parsed[k] for k in fields} == fields


@pytest.mark.parametrize("name", ["Snapshot.PNG", "overview image 24h.PNG", "VID1_A1.jpg"])
def test_spheroid_names_of_another_form(name):
    assert parse_filename(EXAMPLE, name) is None


@pytest.mark.parametrize("name,fields", [
    ("VID2359_F8_1_04d12h00m-1.jpg", dict(vid="2359", well="F8", variant="1")),
    ("BF_D10_1_06d12h00m-1L.jpg", dict(vid=None, well="D10", channel="BF", variant="1L")),
    ("Brightfield_A1_1_00d00h00m.tif", dict(vid=None, well="A1", channel="Brightfield", channel_norm="BF")),
    ("PC_H2_1_00d00h00m.tif", dict(vid=None, well="H2", channel="PC", channel_norm="PC")),
    ("Phase_A1_1_00d00h00m.tif", dict(channel="Phase", channel_norm="PC")),
    ("BF_A1_1_00d00h00m.tif", dict(channel="BF", channel_norm="BF")),
    ("VID1_A1_1_00d00h00m.jpg", dict(channel="jpg", channel_norm="jpg")),
])
def test_spheroid_annotation_copies_and_channels(name, fields):
    parsed = parse_filename(EXAMPLE, name)
    assert {k: parsed[k] for k in fields} == fields


def _leaf(fields, pattern=r"^(?P<sample>LEAF-\d+)_day(?P<day>\d+)(?:_(?P<side>top|bottom))?(?:_(?P<n>\w+))?\.(?:png|jpe?g)$"):
    """An invented naming scheme: LEAF-0007_day03_top.png."""
    return Dataset({
        "id": "leaf_discs", "title": "Leaf discs",
        "metadata": {"required": ["sample_id"], "fields": {"sample_id": {"header": "Sample ID"}}},
        "images": {"extensions": [".png"], "archives": [{"zip": "leaves.zip", "folder_level": 1}],
                   "filename": {"pattern": pattern, "fields": fields}},
    }, "leaf.yaml")


def test_another_naming_scheme():
    leaf = _leaf({
        "sample_id": {"groups": ["sample"]},
        "day": {"groups": ["day"], "type": "int"},
        "side": {"groups": ["side"], "else_extension": {"jpeg": "jpg"}, "upper": True},
        "side_norm": {"copy": "side", "synonyms": {"TOP": "adaxial", "BOTTOM": "abaxial"}},
        "hours": {"sum": {"day": 24}},
    })
    assert parse_filename(leaf, "LEAF-0007_day03_top.png") == {
        "sample_id": "LEAF-0007", "day": 3, "side": "TOP", "side_norm": "adaxial", "hours": 72,
    }
    # No side in the name: the file type stands in, as the spheroid channel does.
    assert parse_filename(leaf, "LEAF-0007_day00.jpeg")["side"] == "JPG"
    assert parse_filename(leaf, "LEAF-0007_day00.jpeg")["hours"] == 0
    assert parse_filename(leaf, "leaf-0007_day03.png") is None  # the pattern is case-sensitive


def test_missing_sum_group_and_non_number():
    leaf = _leaf({"total": {"sum": {"day": 1, "n": 10}}, "n": {"groups": ["n"], "type": "int"}})
    # An optional group that is absent makes the sum unknown, not zero.
    assert parse_filename(leaf, "LEAF-1_day2.png") == {"total": None, "n": None}
    # A word where a number belongs: the name has another form.
    assert parse_filename(leaf, "LEAF-1_day2_abc.png") is None
    assert parse_filename(leaf, "LEAF-1_day2_5.png") == {"total": 52, "n": 5}
