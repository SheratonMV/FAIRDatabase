"""Catalog walking and matching on synthetic zips. No database."""
import io
import json
import zipfile

from PIL import Image

from plugins.imagehub import config
from plugins.imagehub.ingest import (
    load_match_index, make_preview, match_image, read_member, walk_images,
)
from plugins.imagehub.tests import synthetic

EXAMPLE = config.Dataset(synthetic.example_raw(), "example")
NESTED = EXAMPLE.images["annotation_archive"]["nested_prefix"] + "Set/10.zip"


def _with_inferred(*experiments):
    raw = synthetic.example_raw()
    raw["images"]["match"]["infer_single"] = {"field": "vid", "groups": list(experiments)}
    return config.Dataset(raw, "example with inferred")


def _jpeg():
    out = io.BytesIO()
    Image.new("RGB", (8, 6)).save(out, "JPEG")
    return out.getvalue()


def _disk(tmp_path):
    with zipfile.ZipFile(tmp_path / "NK.zip", "w") as zf:
        zf.writestr("NK/Exp one/images/VID1_A1_1_00d01h00m.jpg", _jpeg())
        zf.writestr("NK/Exp one/images/Snapshot.PNG", b"x")
        zf.writestr("NK/Exp one/notes.pptx", b"x")
        zf.writestr("NK/Exp one/__MACOSX/._VID1_A1_1_00d01h00m.jpg", b"x")
        zf.writestr("NK/Exp one/raw.zip", b"x")
        # A copy listed under images.skip: left out.
        zf.writestr("NK/Copy of Single experiment/VID9_A1_1_00d00h00m.tif", b"x")
    with zipfile.ZipFile(tmp_path / "Single experiment.zip", "w") as zf:
        # folder_level 1: the top folder is the experiment.
        zf.writestr("Single experiment/VID9_A1_1_00d00h00m.tif", b"x")
        zf.writestr("VID9_A2_1_00d00h00m.tif", b"x")
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("set/VID1_A1_1_00d01h00m-1.jpg", _jpeg())
        zf.writestr("set/via.json", json.dumps({}))
    with zipfile.ZipFile(tmp_path / "Annotation.zip", "w") as zf:
        zf.writestr(NESTED, inner.getvalue())
        zf.writestr("Annotation/other/Stimulated.zip", b"x")
    return str(tmp_path)


def test_walk_finds_images_and_reports_the_rest(tmp_path):
    walked = walk_images(_disk(tmp_path), dataset=EXAMPLE)
    folders = {i["source_member"]: i["folder"] for i in walked["images"]}
    nested = NESTED + "!/set/VID1_A1_1_00d01h00m-1.jpg"
    assert folders == {
        "NK/Exp one/images/VID1_A1_1_00d01h00m.jpg": "Exp one",
        "Single experiment/VID9_A1_1_00d00h00m.tif": "Single experiment",
        "VID9_A2_1_00d00h00m.tif": None,
        nested: None,
    }
    assert walked["unparsed"] == [("NK.zip", "NK/Exp one/images/Snapshot.PNG")]
    assert {n[1] for n in walked["nested"]} == {"NK/Exp one/raw.zip", "Annotation/other/Stimulated.zip"}
    assert "Btk.zip" in walked["missing_zips"]


def test_read_member_plain_and_nested(tmp_path):
    disk = _disk(tmp_path)
    assert read_member("NK.zip", "NK/Exp one/images/VID1_A1_1_00d01h00m.jpg", disk) == _jpeg()
    nested = NESTED + "!/set/VID1_A1_1_00d01h00m-1.jpg"
    assert read_member("Annotation.zip", nested, disk) == _jpeg()


def test_without_a_nested_prefix_no_nested_zip_is_opened(tmp_path):
    raw = synthetic.example_raw()
    del raw["images"]["annotation_archive"]["nested_prefix"]
    walked = walk_images(_disk(tmp_path), dataset=config.Dataset(raw, "no prefix"))
    assert not any("!/" in i["source_member"] for i in walked["images"])
    assert NESTED in {n[1] for n in walked["nested"]}


def _index():
    return {
        "by_group": {
            ("Exp one (AA)", "1", "A1"): {"w1"},
            ("Exp one (AA)", "1", "A2"): {"w2", "w3"},
            ("Other", "2", "B1"): {"w4"},
        },
        "by_keys": {("1", "A1"): {"w1"}, ("1", "A2"): {"w2", "w3"}, ("2", "B1"): {"w4"}},
        "group_of": {"w1": "Exp one (AA)", "w2": "Exp one (AA)", "w3": "Exp one (AA)", "w4": "Other"},
        "names": {"expone": "Exp one (AA)", "other": "Other"},
    }


def _match(folder, vid, well):
    return match_image({"folder": folder, "vid": vid, "well": well}, _index(), dataset=EXAMPLE)


def test_match_outcomes():
    hit = _match("Exp one", "1", "A1")
    assert (hit["well_id"], hit["match_status"], hit["experiment"]) == ("w1", "matched", "Exp one (AA)")

    several = _match("Exp one", "1", "A2")
    assert several["well_id"] is None and several["match_status"] == "ambiguous"
    assert several["candidates"] == {"w2", "w3"}

    assert _match("Exp one", "1", "H9")["match_reason"] == "not_in_experiment"
    assert _match("Exp one", None, "A1")["match_reason"] == "no_vid_in_name"

    unknown = _match("EXP18 no metadata", "1", "A1")
    assert unknown["match_reason"] == "no_metadata_for_experiment"
    assert unknown["experiment"] == "EXP18 no metadata"


def test_alias_from_the_config_links_a_differently_named_folder():
    index = _index()
    index["names"]["exampleexperiment1"] = "Example experiment 1"
    index["by_group"][("Example experiment 1", "5", "C1")] = {"w5"}
    index["group_of"]["w5"] = "Example experiment 1"
    hit = match_image({"folder": "Example folder 1", "vid": "5", "well": "C1"}, index, dataset=EXAMPLE)
    assert (hit["match_status"], hit["well_id"]) == ("matched", "w5")


def test_inferred_only_for_listed_experiment_with_one_vid():
    index = _index()
    index["values_of"] = {"Exp one (AA)": {"1"}, "Other": {"2", "3"}}
    both = _with_inferred("Exp one (AA)", "Other")
    image = {"folder": "Exp one", "vid": None, "well": "A1"}
    hit = match_image(image, index, dataset=both)
    assert (hit["match_status"], hit["well_id"], hit["vid"]) == ("inferred", "w1", "1")

    missing = match_image({"folder": "Exp one", "vid": None, "well": "H9"}, index, dataset=both)
    assert (missing["match_status"], missing["vid"]) == ("unmatched", None)

    two_vids = match_image({"folder": "Other", "vid": None, "well": "B1"}, index, dataset=both)
    assert two_vids["match_reason"] == "no_vid_in_name"

    not_listed = match_image(image, index, dataset=_with_inferred("Other"))
    assert not_listed["match_status"] == "unmatched"
    assert not_listed["match_reason"] == "no_vid_in_name"


def test_nested_set_is_inferred_through_its_experiment_hint():
    index = _index()
    index["values_of"] = {"Exp one (AA)": {"1"}}
    image = {"folder": None, "vid": None, "well": "A1", "experiment_hint": "Exp one (AA)"}
    hit = match_image(image, index, dataset=_with_inferred("Exp one (AA)"))
    assert (hit["match_status"], hit["well_id"], hit["vid"]) == ("inferred", "w1", "1")
    assert hit["experiment"] == "Exp one (AA)"


def test_match_annotation_image_without_folder_takes_experiment_of_well():
    assert _match(None, "2", "B1")["experiment"] == "Other"
    assert _match(None, "9", "A1")["match_reason"] == "not_in_metadata"


def test_make_preview_tiff_keeps_size():
    out = io.BytesIO()
    Image.new("L", (16, 12), 200).save(out, "TIFF")
    preview = Image.open(io.BytesIO(make_preview(out.getvalue())))
    assert preview.format == "JPEG" and preview.size == (16, 12)


def test_make_preview_refuses_other_pixel_formats_and_junk():
    out = io.BytesIO()
    Image.new("I;16", (4, 4)).save(out, "TIFF")
    assert make_preview(out.getvalue()) is None
    assert make_preview(b"not an image") is None


class _Rows:
    """A cursor that answers the one SELECT of load_match_index."""

    def __init__(self, rows):
        self.rows = rows

    def execute(self, statement, params=None):
        assert statement.startswith("SELECT id, fields FROM _fd.imagehub_wells WHERE dataset")

    def fetchall(self):
        return self.rows


def _leaf(**match):
    raw = {
        "id": "leaf_discs",
        "title": "Leaf discs",
        "metadata": {"required": ["sample_id"], "fields": {
            "sample_id": {"header": "Sample ID"}, "side": {"header": "Side"},
            "plot": {"header": "Plot"},
        }},
        "images": {
            "extensions": [".png"],
            "archives": [{"zip": "leaves.zip", "folder_level": 1}],
            "filename": {
                "pattern": r"^(?P<s>LEAF-\d+)_day(?P<d>\d+)_(?P<side>top|bottom)\.png$",
                "ignore_case": True,
                "fields": {"sample_id": {"groups": ["s"], "upper": True},
                           "side": {"groups": ["side"]}, "day": {"groups": ["d"], "type": "int"}},
            },
            "match": {"keys": [{"image": "sample_id", "sample": "sample_id", "upper": True},
                               {"image": "side", "sample": "side"}], **match},
        },
    }
    return config.Dataset(raw, "leaf.yaml")


def test_matching_by_other_keys_without_groups_ignores_the_folder():
    leaf = _leaf()
    index = load_match_index(_Rows([
        ("r1", {"sample_id": "leaf-7", "side": "top", "plot": "north"}),
        ("r2", {"sample_id": "LEAF-7", "side": "bottom"}),
        ("r3", {"side": "top"}),
    ]), dataset=leaf)
    image = {"folder": "any folder", "sample_id": "LEAF-7", "side": "top"}
    hit = match_image(image, index, dataset=leaf)
    # Upper-cased on both sides; the folder names no group and does not block.
    assert (hit["match_status"], hit["well_id"], hit["experiment"]) == ("matched", "r1", "any folder")
    assert match_image({**image, "side": None}, index, dataset=leaf)["match_reason"] == "no_side_in_name"
    assert match_image({**image, "sample_id": "LEAF-8"}, index, dataset=leaf)["match_reason"] == "not_in_metadata"


def test_a_group_field_scopes_matching_to_the_named_group():
    leaf = _leaf(group_field="plot")
    index = load_match_index(_Rows([
        ("r1", {"sample_id": "LEAF-7", "side": "top", "plot": "north"}),
        ("r2", {"sample_id": "LEAF-7", "side": "top", "plot": "south"}),
    ]), dataset=leaf)
    image = {"folder": "North", "sample_id": "LEAF-7", "side": "top"}
    assert match_image(image, index, dataset=leaf)["well_id"] == "r1"
    several = match_image({**image, "folder": None}, index, dataset=leaf)
    assert (several["match_status"], several["candidates"]) == ("ambiguous", {"r1", "r2"})
    unknown = match_image({**image, "folder": "East"}, index, dataset=leaf)
    assert unknown["match_reason"] == "no_metadata_for_experiment"


def test_an_inferred_value_goes_into_fields_too():
    index = _index()
    index["values_of"] = {"Exp one (AA)": {"1"}}
    image = {"folder": "Exp one", "vid": None, "well": "A1", "fields": {"well": "A1"}}
    hit = match_image(image, index, dataset=_with_inferred("Exp one (AA)"))
    assert hit["fields"] == {"well": "A1", "vid": "1"}
    assert hit["match_reason"] == "vid_inferred_from_experiment"

