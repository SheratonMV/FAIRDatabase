"""Extra image values from a csv: ``flask imagehub import-values``.

The csv is keyed by ``(source_zip, source_member)``, the catalog's natural key. Every
other column must be an extra field of the dataset (``images.extra_fields``); a csv
may hold some of them. Values are checked against the declared type. An empty cell
removes that key from the image. Keys that are not in the csv, parsed file-name keys
and undeclared keys are never touched.

``read_values`` and ``plan_values`` are pure; ``own_images``, ``other_owner_count`` and
``write_values`` run SQL. Problems and counts never contain values.
"""
import csv
import math

from psycopg2.extras import Json, execute_values

KEY_COLUMNS = ("source_zip", "source_member")


class ValuesError(ValueError):
    """The csv cannot be used at all."""


def _convert(text, kind):
    """A csv cell -> a value of the declared type; None for an empty cell."""
    text = (text or "").strip()
    if not text:
        return None
    if kind == "text":
        return text
    if kind == "int":
        try:
            return int(text)
        except ValueError:
            raise ValueError("is not a whole number") from None
    try:
        value = float(text)
    except ValueError:
        raise ValueError("is not a number") from None
    if not math.isfinite(value):
        raise ValueError("is not a finite number")
    return value


def read_values(lines, extra_fields):
    """csv lines -> (values, columns, problems).

    values:   ``{(source_zip, source_member): {field: value or None}}``
    columns:  the extra fields the csv sets, in csv order
    problems: ``[(line, reason)]``; a row with a problem is left out entirely.
    """
    if not extra_fields:
        raise ValuesError("this dataset declares no images.extra_fields")
    reader = csv.DictReader(lines)
    header = list(reader.fieldnames or ())
    missing = [c for c in KEY_COLUMNS if c not in header]
    if missing:
        raise ValuesError("missing column(s): " + ", ".join(missing))
    columns = [c for c in header if c not in KEY_COLUMNS]
    unknown = [c for c in columns if c not in extra_fields]
    if unknown:
        raise ValuesError("not an extra field of this dataset: " + ", ".join(unknown)
                          + "; declared: " + ", ".join(sorted(extra_fields)))
    if not columns:
        raise ValuesError("no value columns: name one or more extra fields")
    if len(set(header)) != len(header):
        raise ValuesError("a column is listed twice")
    values, problems, seen = {}, [], set()
    for line, row in enumerate(reader, start=2):
        key = tuple((row.get(c) or "").strip() for c in KEY_COLUMNS)
        if not all(key):
            problems.append((line, "empty source_zip or source_member"))
            continue
        if key in seen:
            problems.append((line, "source_zip + source_member listed twice"))
            values.pop(key, None)
            continue
        seen.add(key)
        converted, bad = {}, None
        for name in columns:
            try:
                converted[name] = _convert(row.get(name), extra_fields[name]["type"])
            except ValueError as exc:
                bad = f"{name} {exc}"
                break
        if bad:
            problems.append((line, bad))
            continue
        values[key] = converted
    return values, columns, problems


def plan_values(values, images, columns):
    """What to change in the owner's images.

    images: ``{(source_zip, source_member): {"id", "fields"}}`` (the owner's own).
    -> ``{"updates": [(image id, {set}, [remove])], "counts": {...}}``
    """
    per_field = {name: {"set": 0, "changed": 0, "removed": 0, "unchanged": 0}
                 for name in columns}
    counts = {"csv_rows": len(values), "joined": 0, "not_in_own_catalog": 0,
              "images_to_write": 0, "fields": per_field}
    updates = []
    for key, row in values.items():
        image = images.get(key)
        if image is None:
            counts["not_in_own_catalog"] += 1
            continue
        counts["joined"] += 1
        current = image["fields"] or {}
        to_set, to_remove = {}, []
        for name in columns:
            value, present = row[name], name in current
            if value is None:
                if present:
                    to_remove.append(name)
                    per_field[name]["removed"] += 1
                else:
                    per_field[name]["unchanged"] += 1
            elif not present:
                to_set[name] = value
                per_field[name]["set"] += 1
            elif current[name] != value:
                to_set[name] = value
                per_field[name]["changed"] += 1
            else:
                per_field[name]["unchanged"] += 1
        if to_set or to_remove:
            updates.append((image["id"], to_set, to_remove))
    counts["images_to_write"] = len(updates)
    return {"updates": updates, "counts": counts}


def own_images(cur, owner_id, dataset_id, names):
    """The owner's images of the dataset with the values of these fields only."""
    cur.execute(
        "SELECT id, source_zip, source_member, "
        "(SELECT COALESCE(jsonb_object_agg(e.key, e.value), '{}'::jsonb) "
        " FROM jsonb_each(fields) AS e WHERE e.key = ANY(%s::text[])) "
        "FROM _fd.imagehub_images WHERE owner_id = %s AND dataset = %s",
        (list(names), owner_id, dataset_id),
    )
    return {(z, m): {"id": str(i), "fields": f} for i, z, m, f in cur.fetchall()}


def other_owner_count(cur, owner_id, dataset_id, keys):
    """How many of these keys are catalogued under another owner: a count only."""
    if not keys:
        return 0
    zips, members = zip(*keys)
    cur.execute(
        "SELECT count(*) FROM _fd.imagehub_images i "
        "JOIN unnest(%s::text[], %s::text[]) AS k(z, m) "
        "ON i.source_zip = k.z AND i.source_member = k.m "
        "WHERE i.dataset = %s AND i.owner_id <> %s",
        (list(zips), list(members), dataset_id, owner_id),
    )
    return cur.fetchone()[0]


def write_values(cur, owner_id, dataset_id, updates):
    """Apply the plan. Only rows of ``owner_id`` in ``dataset_id`` change, and only
    the planned keys: ``fields = (fields - removed) || set``. -> rows updated."""
    if not updates:
        return 0
    cur.execute("CREATE TEMP TABLE imagehub_incoming_values "
                "(id uuid, set_values jsonb, removed text[]) ON COMMIT DROP")
    execute_values(
        cur, "INSERT INTO imagehub_incoming_values VALUES %s",
        [(image_id, Json(to_set), to_remove) for image_id, to_set, to_remove in updates],
        template="(%s::uuid, %s::jsonb, %s::text[])", page_size=5000,
    )
    cur.execute(
        "UPDATE _fd.imagehub_images i "
        "SET fields = (i.fields - v.removed) || v.set_values, updated_at = now() "
        "FROM imagehub_incoming_values v "
        "WHERE i.id = v.id AND i.owner_id = %s AND i.dataset = %s",
        (owner_id, dataset_id),
    )
    written = cur.rowcount
    cur.execute("DROP TABLE imagehub_incoming_values")
    return written
