"""values.py: the csv of extra image values and the plan. No database; invented data."""
import io

import pytest

from plugins.imagehub import values

EXTRA = {
    "disc_area": {"type": "float"},
    "lesions": {"type": "int"},
    "rater_note": {"type": "text"},
}


def _csv(header, *rows):
    return io.StringIO("\n".join([header, *rows]) + "\n")


def test_values_are_read_with_their_declared_type():
    found, columns, problems = values.read_values(_csv(
        "source_zip,source_member,disc_area,lesions,rater_note",
        "a.zip,t/LEAF-0001_day01_top.png,12.5,3, dry edge ",
        "a.zip,t/LEAF-0002_day01_top.png,,,",
    ), EXTRA)
    assert problems == [] and columns == ["disc_area", "lesions", "rater_note"]
    assert found[("a.zip", "t/LEAF-0001_day01_top.png")] == {
        "disc_area": 12.5, "lesions": 3, "rater_note": "dry edge"}
    # An empty cell means: remove the key.
    assert found[("a.zip", "t/LEAF-0002_day01_top.png")] == {
        "disc_area": None, "lesions": None, "rater_note": None}


def test_a_csv_may_set_some_of_the_fields():
    found, columns, _ = values.read_values(_csv("source_member,source_zip,lesions", "m.png,a.zip,2"), EXTRA)
    assert columns == ["lesions"] and found[("a.zip", "m.png")] == {"lesions": 2}


@pytest.mark.parametrize("header, message", [
    ("source_zip,disc_area", "missing column(s): source_member"),
    ("source_zip,source_member,colour", "not an extra field of this dataset: colour"),
    ("source_zip,source_member,day", "not an extra field"),
    ("source_zip,source_member", "no value columns"),
    ("source_zip,source_member,lesions,lesions", "listed twice"),
])
def test_unusable_csvs_are_refused(header, message):
    with pytest.raises(values.ValuesError, match=message.replace("(", r"\(").replace(")", r"\)")):
        values.read_values(_csv(header, "a.zip,m.png,1,1"), EXTRA)


def test_a_dataset_without_extra_fields_refuses_a_csv():
    with pytest.raises(values.ValuesError, match="declares no images.extra_fields"):
        values.read_values(_csv("source_zip,source_member,x"), {})


@pytest.mark.parametrize("row, reason", [
    ("a.zip,m.png,abc,1", "disc_area is not a number"),
    ("a.zip,m.png,inf,1", "disc_area is not a finite number"),
    ("a.zip,m.png,nan,1", "disc_area is not a finite number"),
    ("a.zip,m.png,1.0,1.5", "lesions is not a whole number"),
    (",m.png,1.0,1", "empty source_zip or source_member"),
])
def test_bad_rows_are_left_out_with_a_reason_and_no_value(row, reason):
    found, _, problems = values.read_values(_csv("source_zip,source_member,disc_area,lesions", row), EXTRA)
    assert found == {} and problems == [(2, reason)]


def test_a_key_listed_twice_drops_both_rows():
    found, _, problems = values.read_values(
        _csv("source_zip,source_member,lesions", "a.zip,m.png,1", "a.zip,m.png,2"), EXTRA)
    assert found == {} and problems == [(3, "source_zip + source_member listed twice")]


def test_plan_counts_set_changed_removed_and_unchanged():
    found, columns, _ = values.read_values(_csv(
        "source_zip,source_member,disc_area,lesions",
        "a.zip,new.png,1.5,2",
        "a.zip,same.png,2.0,3",
        "a.zip,changed.png,9.0,3",
        "a.zip,cleared.png,,",
        "a.zip,elsewhere.png,1.0,1",
    ), EXTRA)
    images = {
        ("a.zip", "new.png"): {"id": "i-new", "fields": {}},
        ("a.zip", "same.png"): {"id": "i-same", "fields": {"disc_area": 2.0, "lesions": 3}},
        ("a.zip", "changed.png"): {"id": "i-changed", "fields": {"disc_area": 2.0, "lesions": 3}},
        ("a.zip", "cleared.png"): {"id": "i-cleared", "fields": {"disc_area": 2.0}},
    }
    plan = values.plan_values(found, images, columns)
    c = plan["counts"]
    assert (c["csv_rows"], c["joined"], c["not_in_own_catalog"], c["images_to_write"]) == (5, 4, 1, 3)
    assert c["fields"]["disc_area"] == {"set": 1, "changed": 1, "removed": 1, "unchanged": 1}
    assert c["fields"]["lesions"] == {"set": 1, "changed": 0, "removed": 0, "unchanged": 3}
    assert sorted(plan["updates"]) == [
        ("i-changed", {"disc_area": 9.0}, []),
        ("i-cleared", {}, ["disc_area"]),
        ("i-new", {"disc_area": 1.5, "lesions": 2}, []),
    ]


def test_a_second_plan_on_the_written_values_changes_nothing():
    found, columns, _ = values.read_values(_csv("source_zip,source_member,lesions", "a.zip,m.png,4"), EXTRA)
    images = {("a.zip", "m.png"): {"id": "i", "fields": {"lesions": 4}}}
    assert values.plan_values(found, images, columns)["updates"] == []
