"""config.py: loading and checking dataset configs. No database."""
import copy
import os

import pytest
import yaml

from plugins.imagehub import config
from plugins.imagehub.config import ConfigError, Dataset

EXAMPLE = os.path.join(config.DATASET_DIRS[0], "spheroid_example.yaml")


def _example():
    with open(EXAMPLE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _minimal():
    return {
        "id": "leaf_discs",
        "title": "Leaf discs",
        "metadata": {"required": ["sample_id"], "fields": {"sample_id": {"header": "Sample ID"}}},
        "images": {
            "extensions": [".png"],
            "archives": [{"zip": "leaves.zip", "folder_level": 1}],
            "filename": {"pattern": r"^(?P<sample>[A-Z]+-\d+)_day(?P<day>\d+)\.png$",
                         "fields": {"sample_id": {"groups": ["sample"]}, "day": {"groups": ["day"], "type": "int"}}},
        },
    }


def test_shipped_configs_load_and_the_example_is_marked():
    loaded = config.load_dir(config.DATASET_DIRS[0])
    assert "spheroid_example" in loaded
    assert loaded["spheroid_example"].example is True


def test_a_minimal_config_without_spheroid_fields_is_enough():
    dataset = Dataset(_minimal(), "leaf.yaml")
    assert dataset.annotations == {} and dataset.tokens_re is None


def _error(raw):
    with pytest.raises(ConfigError) as info:
        Dataset(raw, "bad.yaml")
    return str(info.value)


def _changed(change):
    raw = copy.deepcopy(_example())
    change(raw)
    return _error(raw)


def test_unknown_keys_are_refused_with_their_place():
    message = _changed(lambda r: r["images"].update(archive=[]))
    assert message.startswith("bad.yaml: images: unknown key(s) archive")


@pytest.mark.parametrize("change, part", [
    (lambda r: r.update(id="Bad id"), "id:"),
    (lambda r: r.update(id="x" * 41), "id:"),
    (lambda r: r["images"]["filename"].update(pattern="(unclosed"), "does not compile"),
    (lambda r: r["images"]["filename"]["fields"]["well"].update(groups=["nope"]), "no group 'nope'"),
    (lambda r: r["metadata"]["fields"]["concentration"].update(header_regex="^Conc$"), "named group(s) unit"),
    (lambda r: r["annotations"].update(annotator_pattern="_(AA)"), "named group(s) label"),
    (lambda r: r["metadata"].update(required=["missing_field"]), "no field 'missing_field'"),
    (lambda r: r["metadata"]["derived"]["vids"].update(steps=["shout"]), "unknown step 'shout'"),
    (lambda r: r["metadata"]["derived"]["vids"].update({"from": "nope"}), "no field 'nope'"),
    (lambda r: r["metadata"]["fields"]["vid"].update(header_regex="(?P<unit>x)"), "exactly one of header"),
    (lambda r: r["images"]["archives"][0].update(zip="/etc/passwd"), "relative to the data root"),
    (lambda r: r["images"]["archives"][0].update(zip="../outside.zip"), "relative to the data root"),
    (lambda r: r["images"]["archives"][0].update(zip="C:\\data.zip"), "relative to the data root"),
    (lambda r: r["images"]["archives"][0].update(folder_level=0), "whole number >= 1"),
    (lambda r: r["images"]["filename"]["fields"]["channel_norm"].update(copy="later"), "listed before"),
    (lambda r: r["metadata"].update(fields=["vid"]), "must be a mapping"),
    (lambda r: r["annotations"].update(format="coco"), "only via"),
    (lambda r: r["images"]["match"].pop("keys"), "missing key keys"),
    (lambda r: r["images"]["match"].update(keys=[]), "non-empty list"),
    (lambda r: r["images"]["match"]["keys"][0].update(image="plate"), "no field 'plate' in images.filename"),
    (lambda r: r["images"]["match"]["keys"][0].update(sample="plate"), "no field 'plate' in metadata"),
    (lambda r: r["images"]["match"]["keys"][1].update(image="vid"), "listed twice"),
    (lambda r: r["images"]["match"].update(group_field="plate"), "no field 'plate' in metadata"),
    (lambda r: r["images"]["match"].pop("group_field"), "needs images.match.group_field"),
    (lambda r: r["images"]["match"]["infer_single"].update(field="channel"), "in images.match.keys"),
    (lambda r: r["ui"]["filters"][0].update(type="fuzzy"), "select, text or range"),
    (lambda r: r["ui"]["filters"][0].update(field="sample.nope"), "no sample field 'nope'"),
    (lambda r: r["ui"]["filters"][0].update(field="well"), "must be one of"),
    (lambda r: r["ui"]["filters"][1].update(param="experiment"), "already used"),
    (lambda r: r["ui"]["filters"][1].update(param="page"), "already used"),
    (lambda r: r["ui"]["filters"][-1].update(field="image.channel"), "whole numbers"),
    (lambda r: r["ui"]["filters"][-1].update(params=["from_day"]), "two params"),
    (lambda r: r["ui"]["filters"][0].update(scale=2), "only goes with type range"),
    (lambda r: r["ui"]["columns"][0].update(fields=["group"]), "exactly one of field, fields"),
    (lambda r: r["ui"]["columns"][3].update(format="hours"), "only minutes"),
    (lambda r: r["export"].pop("sections"), "missing key sections"),
    (lambda r: r["export"]["sections"][0]["columns"][2].update({"from": "sample.nope"}), "no sample field 'nope'"),
    (lambda r: r["export"]["sections"][0]["columns"][2].pop("from"), "needs from, unless"),
    (lambda r: r["export"]["sections"][0]["columns"].append({"name": "vid", "from": "image.vid", "description": "x"}), "listed twice"),
    (lambda r: r["export"].pop("notes"), "needs export.notes"),
    (lambda r: r["export"]["sections"].append({"annotations": "Again"}), "annotations is listed twice"),
    (lambda r: r["export"]["sheet_columns"]["groups"][0].update(match="(unclosed"), "does not compile"),
    (lambda r: r["export"]["sections"][3]["columns"][1]["steps"].append({"replace": {"pattern": "("}}), "missing key with"),
    (lambda r: r["export"].update(file_prefix="Bad prefix"), "export.file_prefix"),
    (lambda r: r["dashboard"].update(group="nope"), "no column 'nope' in export.sections"),
    (lambda r: r["dashboard"].update(label="{experiment} {nope}"), "no column 'nope'"),
    (lambda r: r["dashboard"]["units"].update(tissue="nope"), "dashboard.units.tissue"),
    (lambda r: r["dashboard"]["sample_fields"].update(tissue="sample.tissue"), "not in dashboard.key"),
    (lambda r: r["dashboard"]["sample_fields"].update(vid="image.vid"), "must be one of: group, sample"),
    (lambda r: r["dashboard"]["tabs"].update(extra="X"), "unknown key(s) extra"),
    (lambda r: r["dashboard"].update(colour="x"), "unknown key(s) colour"),
    (lambda r: r.pop("export"), "dashboard: needs export"),
])
def test_bad_values_are_refused(change, part):
    assert part in _changed(change)


def test_a_non_mapping_file_is_refused():
    assert "must be a mapping" in _error(["not", "a", "config"])


def test_yaml_is_loaded_safely(tmp_path):
    path = tmp_path / "evil.yaml"
    path.write_text("id: !!python/object/apply:os.system ['true']\n")
    with pytest.raises(ConfigError, match="not valid YAML"):
        config.load_file(str(path))


def test_large_files_are_refused(tmp_path, monkeypatch):
    path = tmp_path / "big.yaml"
    path.write_text("# " + "x" * 100 + "\n")
    monkeypatch.setattr(config, "MAX_FILE_BYTES", 50)
    with pytest.raises(ConfigError, match="larger than"):
        config.load_file(str(path))


def test_duplicate_ids_are_refused(tmp_path):
    for name in ("a.yaml", "b.yaml"):
        (tmp_path / name).write_text(yaml.safe_dump(_minimal()))
    with pytest.raises(ConfigError, match="also used by a.yaml"):
        config.load_dir(str(tmp_path))


def test_active_dataset(monkeypatch):
    example = Dataset(_example(), "example.yaml")
    own = Dataset(_minimal(), "own.yaml")
    monkeypatch.delenv("IMAGEHUB_DATASET", raising=False)
    assert config.get(available={"spheroid_example": example}) is example
    assert config.get(available={"spheroid_example": example, "leaf_discs": own}) is own
    assert config.get("spheroid_example", available={"spheroid_example": example, "leaf_discs": own}) is example
    monkeypatch.setenv("IMAGEHUB_DATASET", "spheroid_example")
    assert config.get(available={"spheroid_example": example, "leaf_discs": own}) is example
    with pytest.raises(ConfigError, match="no dataset 'other'"):
        config.get("other", available={"leaf_discs": own})
    monkeypatch.delenv("IMAGEHUB_DATASET")
    second = Dataset({**_minimal(), "id": "leaf_two"}, "two.yaml")
    with pytest.raises(ConfigError, match="set IMAGEHUB_DATASET"):
        config.get(available={"leaf_discs": own, "leaf_two": second})


# ── extra image fields ─────────────────────────────────────────────────────────

EXTRA = {
    "disc_area": {"type": "float", "label": "Disc area", "unit": "mm2", "decimals": 1},
    "lesions": {"type": "int"},
    "rater_note": {"type": "text"},
}


def _with_extra():
    raw = _minimal()
    raw["metadata"]["fields"]["plot"] = {"header": "Plot"}
    raw["images"]["extra_fields"] = copy.deepcopy(EXTRA)
    return raw


def test_configs_without_extra_fields_are_unchanged():
    for ds in config.load_dir(config.DATASET_DIRS[0]).values():
        assert ds.extra_fields == {} and ds.float_fields == set()
    assert Dataset(_minimal(), "minimal").int_fields == {"day"}


def test_extra_fields_are_image_fields_of_their_type():
    raw = _with_extra()
    raw["ui"] = {
        "filters": [
            {"field": "image.disc_area", "type": "range", "params": ["area_from", "area_to"]},
            {"field": "image.lesions", "type": "range", "params": ["lesions_from", "lesions_to"]},
            {"param": "note", "field": "image.rater_note", "type": "select"},
        ],
        "sort": ["image.disc_area", "image.lesions"],
        "columns": [{"label": "Area", "field": "image.disc_area"}],
        "image_details": [{"label": "Area / lesions", "fields": ["image.disc_area", "image.lesions"]}],
    }
    ds = Dataset(raw, "with extra")
    assert ds.extra_fields == EXTRA
    assert ds.float_fields == {"disc_area"} and ds.int_fields == {"day", "lesions"}
    assert {"sample_id", "day", "disc_area", "lesions", "rater_note"} <= ds.image_fields


def test_extra_fields_can_be_exported():
    raw = _example()
    raw["images"]["extra_fields"] = {"disc_area": {"type": "float"}}
    raw["export"]["sections"][0]["columns"].append(
        {"name": "disc_area", "from": "image.disc_area", "description": "Area"})
    Dataset(raw, "export with extra")


@pytest.mark.parametrize("change, part", [
    (lambda e: e["disc_area"].pop("type"), "missing key type"),
    (lambda e: e["disc_area"].update(type="bool"), "must be int, float or text"),
    (lambda e: e["disc_area"].update(colour="red"), "unknown key(s) colour"),
    (lambda e: e.update(Area={"type": "int"}), "must be a field name"),
    (lambda e: e.update(day={"type": "int"}), "also a field in images.filename.fields"),
    (lambda e: e.update(plot={"type": "text"}), "also a sample field"),
    (lambda e: e.update(source_zip={"type": "text"}), "built-in column"),
    (lambda e: e["lesions"].update(decimals=1), "only goes with type float"),
    (lambda e: e["disc_area"].update(decimals=-1), "whole number >= 0"),
    (lambda e: e["disc_area"].update(label=""), "non-empty text"),
])
def test_bad_extra_fields_are_refused(change, part):
    raw = _with_extra()
    change(raw["images"]["extra_fields"])
    with pytest.raises(ConfigError) as caught:
        Dataset(raw, "bad extra")
    assert part in str(caught.value) and "images.extra_fields" in str(caught.value)


def test_a_range_on_a_text_extra_field_is_refused():
    raw = _with_extra()
    raw["ui"] = {"filters": [{"field": "image.rater_note", "type": "range", "params": ["a", "b"]}]}
    with pytest.raises(ConfigError, match="a range needs an image field of numbers"):
        Dataset(raw, "text range")


def test_an_extra_field_cannot_be_a_match_key():
    raw = _example()
    raw["images"]["extra_fields"] = {"disc_area": {"type": "float"}}
    raw["images"]["match"]["keys"][0]["image"] = "disc_area"
    with pytest.raises(ConfigError, match="no field 'disc_area' in images.filename"):
        Dataset(raw, "extra as key")
