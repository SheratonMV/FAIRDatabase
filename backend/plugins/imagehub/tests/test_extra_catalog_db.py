"""The catalog keeps extra image fields on a re-run. Synthetic leaf discs; database."""
import json

import pytest

from plugins.imagehub.tests import extra_leaf


@pytest.fixture
def world(app, tmp_path, monkeypatch):
    yield from extra_leaf.world(app, tmp_path, monkeypatch)


def _set(world, member_like, values):
    world["sql"]("UPDATE _fd.imagehub_images SET fields = fields || %s::jsonb "
                 "WHERE owner_id = %s AND dataset = %s AND source_member LIKE %s",
                 json.dumps(values), world["a_id"], world["dataset_id"], member_like, commit=True)


def _fields(world, member_like):
    rows = world["sql"]("SELECT fields, updated_at FROM _fd.imagehub_images WHERE owner_id = %s "
                        "AND dataset = %s AND source_member LIKE %s ORDER BY source_member",
                        world["a_id"], world["dataset_id"], member_like)
    return rows


def test_catalog_keeps_extra_fields_and_counts_them_unchanged(world):
    first = world["load"]()
    assert "'inserted': 17" in first
    _set(world, "%LEAF-0001_day01_%", {"disc_area": 12.34, "lesions": 2})
    before = _fields(world, "%LEAF-0001_day01_%")
    # A key that is not declared is not kept: the catalog resets it as before.
    _set(world, "%LEAF-0002_day01_top.png", {"stray": 1})

    again = world["run"]("catalog", "--dataset", world["dataset_id"], "--apply",
                         "--as", world["a_email"])
    assert "APPLIED: {'updated': 1, 'unchanged': 16}" in again, again

    after = _fields(world, "%LEAF-0001_day01_%")
    assert [f for f, _ in after] == [f for f, _ in before]
    assert all(f["disc_area"] == 12.34 and f["lesions"] == 2 and f["sample_id"] == "LEAF-0001"
               for f, _ in after)
    assert [u for _, u in after] == [u for _, u in before]     # not touched at all
    (stray, _), = _fields(world, "%LEAF-0002_day01_top.png")
    assert "stray" not in stray and stray["sample_id"] == "LEAF-0002"


def test_parsed_keys_are_still_replaced_next_to_kept_ones(world):
    world["load"]()
    _set(world, "%LEAF-0003_day03_top.png", {"disc_area": 5.0, "side": "edited"})
    world["run"]("catalog", "--dataset", world["dataset_id"], "--apply", "--as", world["a_email"])
    (fields, _), = _fields(world, "%LEAF-0003_day03_top.png")
    assert fields["side"] == "top" and fields["disc_area"] == 5.0


def test_a_dataset_still_loads_after_an_extra_field_is_removed_from_its_config(world):
    world["load"]()
    _set(world, "%LEAF-0001_%", {"disc_area": 7.5, "lesions": 1})
    plain = world["use"](extra=False)
    assert plain.extra_fields == {}

    client = world["client"]
    page = client.get("/imagehub/ui", query_string={"dataset": plain.id})
    assert page.status_code == 200 and "LEAF-0001" in page.get_data(as_text=True)
    image_id = world["sql"]("SELECT id::text FROM _fd.imagehub_images WHERE owner_id = %s "
                            "AND dataset = %s AND source_member LIKE %s",
                            world["a_id"], plain.id, "%LEAF-0001_day01_top.png")[0][0]
    detail = client.get(f"/imagehub/ui/images/{image_id}")
    assert detail.status_code == 200 and "Disc area" not in detail.get_data(as_text=True)
    found = client.get("/imagehub/api/images", query_string={"dataset": plain.id}).get_json()
    assert found["total"] == 17
    export = world["run"]("export", "--dataset", plain.id, "--as", world["a_email"])
    assert "export" in export.lower()

    # The keys are no longer declared, so the next catalog run resets them.
    dry = world["run"]("catalog", "--dataset", plain.id, "--as", world["a_email"])
    assert "DRY RUN" in dry
    assert all("disc_area" in f for f, _ in _fields(world, "%LEAF-0001_%"))
    applied = world["run"]("catalog", "--dataset", plain.id, "--apply", "--as", world["a_email"])
    assert "'updated': 4" in applied
    assert not any("disc_area" in f for f, _ in _fields(world, "%LEAF-0001_%"))
