"""Metadata ingest for the imagehub plugin.

Reading is separate from writing, so a dry run touches no database. The disk is
only ever opened for reading.
"""
import collections
import csv
import hashlib
import io
import itertools
import json
import os
import zipfile

from openpyxl import load_workbook
from PIL import Image, UnidentifiedImageError
from psycopg2.extras import execute_values

from kernel.audit import record
from kernel.env import get as env_get
from kernel.storage import delete_object, upload_stream

from . import config
from .helpers import (
    UNKNOWN_ANNOTATOR,
    annotator_label,
    dedupe_headers,
    experiment_key,
    experiment_tokens,
    mime_type,
    parse_via,
    storage_key,
    to_json_value,
    to_text,
)
from .rules import apply_steps, parse_filename, value_mapping

DEFAULT_DISK_ROOT = "/mnt/d"


def disk_root_from_env():
    """Where the disk with the zips is mounted: IMAGEHUB_DISK_ROOT, else /mnt/d."""
    return (env_get("IMAGEHUB_DISK_ROOT") or "").strip() or DEFAULT_DISK_ROOT


# Read once at start; restart the app after changing it.
DISK_ROOT = disk_root_from_env()
BUCKET = "imagehub-images"
# A member inside a nested zip is stored as "<nested zip>!/<member>". Only nested
# zips under the dataset's nested_prefix are opened; every other nested archive is
# listed in the report.
NESTED_SEPARATOR = "!/"
NESTED_ARCHIVES = (".zip", ".7z", ".rar")

# Which zips hold images, which folders are copies, how folders map to experiments
# and who annotated what: all of that is in the dataset config (config.py).


def _dataset(dataset):
    """The given dataset config, or the active one."""
    return dataset if dataset is not None else config.get()


def _extensions(ds):
    return tuple(ds.images["extensions"])


def annotation_zip(dataset=None):
    """Name of the zip with annotation sets, or None."""
    return (_dataset(dataset).images.get("annotation_archive") or {}).get("zip")


def _skipped(ds):
    """(zip, folder) copies that are not catalogued."""
    return {(s["zip"], s["folder"]) for s in ds.images.get("skip") or []}


def _match_rules(ds):
    return ds.images.get("match") or {}


def _match_value(key, value):
    return value.upper() if key.get("upper") and isinstance(value, str) else value


def _image_key(ds, image):
    """The values an image is matched on, in ``match.keys`` order."""
    return tuple(_match_value(k, image.get(k["image"])) for k in _match_rules(ds).get("keys") or ())


def _sample_keys(ds, fields):
    """Every key a sample row can be matched by: a list field gives one per item."""
    choices = []
    for key in _match_rules(ds).get("keys") or ():
        value = fields.get(key["sample"])
        values = value if isinstance(value, list) else [value]
        choices.append([_match_value(key, v) for v in values if v is not None])
    return list(itertools.product(*choices))


def _group(ds, fields):
    field = _match_rules(ds).get("group_field")
    return fields.get(field) if field else None


def _name_key(ds, name):
    return experiment_key(name, ds.names_ignore_re)


def _present(values):
    """Field values without the empty ones, as migration 003 stores old rows."""
    return {k: v for k, v in values.items() if v is not None}


def _is_lock_file(name):
    return os.path.basename(name).startswith("~$")


def _iter_sources(source):
    """Yield ``(file name, binary stream)`` for an xlsx, csv, folder or zip."""
    if os.path.isdir(source):
        for name in sorted(os.listdir(source)):
            if name.lower().endswith((".xlsx", ".csv")) and not _is_lock_file(name):
                with open(os.path.join(source, name), "rb") as fh:
                    yield name, fh
    elif source.lower().endswith(".zip"):
        with zipfile.ZipFile(source) as zf:
            for name in sorted(zf.namelist()):
                if name.lower().endswith((".xlsx", ".csv")) and not _is_lock_file(name):
                    yield os.path.basename(name), io.BytesIO(zf.read(name))
    else:
        with open(source, "rb") as fh:
            yield os.path.basename(source), fh


def _iter_sheets(name, stream):
    """Yield ``(sheet name, rows)``; a CSV is one sheet named after the file."""
    if name.lower().endswith(".csv"):
        text = io.TextIOWrapper(stream, encoding="utf-8-sig", newline="")
        yield os.path.splitext(name)[0], [
            [cell if cell != "" else None for cell in row]
            for row in csv.reader(text)
        ]
        return
    workbook = load_workbook(stream, read_only=True, data_only=True)
    try:
        for sheet in workbook.sheetnames:
            yield sheet, list(workbook[sheet].iter_rows(values_only=True))
    finally:
        workbook.close()


def _locate_fields(ds, headers):
    """Where each config field is in a sheet: ``{field: column index}``, the unit of
    each header_regex field, and the labels of fields this sheet does not have."""
    stripped = [h.strip() for h in headers]
    index, units, missing_headers, missing_regex = {}, {}, [], []
    for field, spec in ds.metadata["fields"].items():
        if "header" in spec:
            if spec["header"] in stripped:
                index[field] = stripped.index(spec["header"])
            else:
                missing_headers.append(spec["header"])
            continue
        pattern = ds.header_res[field]
        for i, header in enumerate(stripped):
            match = pattern.match(header)
            if match:
                index[field], units[field] = i, match.group("unit").strip()
                break
        else:
            missing_regex.append(spec.get("label", field))
    return index, units, sorted(missing_headers) + missing_regex


def _parse_row(ds, workbook, sheet, row_number, headers, index, units, row):
    """One sample row: config fields, derived fields and every other column in props."""
    cell = lambda i: row[i] if i is not None and i < len(row) else None
    values = {}
    for field, spec in ds.metadata["fields"].items():
        value = to_text(cell(index.get(field)))
        if spec.get("strip") and value:
            value = value.strip()
        values[field] = value
        if "header_regex" in spec:
            values[spec.get("unit_field", f"{field}_unit")] = units.get(field)
    for field, spec in (ds.metadata.get("derived") or {}).items():
        values[field] = apply_steps(values[spec["from"]], spec["steps"])
    used = set(index.values())
    props = {}
    for i, header in enumerate(headers):
        value = cell(i)
        if i in used or (header.startswith("(no header") and value is None):
            continue
        props[header] = to_json_value(value)
    return {
        **values,
        "dataset": ds.id,
        "fields": _present(values),
        "source_workbook": workbook,
        "source_sheet": sheet,
        "source_row": row_number,
        "props": props,
    }


def _skip_reason(ds, index, row):
    """Why a row is skipped, or None to import it. The second value says whether a
    skipped row still holds data worth a look."""
    md = ds.metadata
    cell = lambda field: (
        to_text(row[index[field]]) if field in index and index[field] < len(row) else None
    )
    missing = next((f for f in md["required"] if cell(f) is None), None)
    if missing is None:
        return None, False
    position = md.get("position")
    filled = sum(c is not None for c in row)
    # A row with nothing (or only a plate position) is blank, not a lost sample.
    if (cell(position) if position else (filled or None)) is None:
        return "skipped_blank", False
    flag = md.get("flag_skipped_with_data")
    raw = lambda field: row[index[field]] if field in index and index[field] < len(row) else None
    with_data = bool(flag) and (
        any(raw(f) is not None for f in flag.get("any_of") or ())
        or ("min_filled" in flag and filled >= flag["min_filled"])
    )
    return f"skipped_no_{missing}", with_data


def read_metadata(source, dataset=None):
    """Read sample rows and legends. Writes nothing.

    Returns ``{"dataset", "wells", "legends", "sheets", "report"}``. ``report`` has one row
    per sheet row that was skipped; imported rows are added by the caller.
    """
    ds = _dataset(dataset)
    md = ds.metadata
    legend = (md.get("legend_sheet") or "").strip().lower()
    wells, legends, sheets, report = [], [], [], []
    for name, stream in _iter_sources(source):
        for sheet, rows in _iter_sheets(name, stream):
            if not rows:
                continue
            if legend and sheet.strip().lower() == legend:
                legends.append({
                    "source_workbook": name,
                    "source_sheet": sheet,
                    "rows": [[to_json_value(c) for c in r] for r in rows],
                })
                continue
            headers = dedupe_headers(rows[0])
            index, units, missing = _locate_fields(ds, headers)
            stats = collections.Counter()
            for row_number, row in enumerate(rows[1:], start=2):
                reason, with_data = _skip_reason(ds, index, row)
                if reason:
                    stats[reason] += 1
                    if with_data:
                        stats[f"{reason}_with_data"] += 1
                    report.append((name, sheet, row_number, reason))
                    continue
                wells.append(_parse_row(ds, name, sheet, row_number, headers, index, units, row))
                stats["wells"] += 1
                for field in md.get("report_missing") or ():
                    if not wells[-1].get(field):
                        stats[f"wells_without_{field}"] += 1
            sheets.append({
                "workbook": name,
                "sheet": sheet,
                "columns": len(headers),
                "missing_core": missing,
                **stats,
            })
    return {"dataset": ds.id, "wells": wells, "legends": legends, "sheets": sheets,
            "report": report}


def derived_mappings(wells, dataset=None):
    """Per derived field: ``{raw: (cleaned list, row count)}``, for review."""
    ds = _dataset(dataset)
    return {
        field: value_mapping(wells, spec["from"], spec["steps"])
        for field, spec in (ds.metadata.get("derived") or {}).items()
    }


def _experiment_folder(archive, member):
    """Experiment folder of a member: the folder at the archive's ``folder_level``
    (1 is the top folder), or None for a member that is not that deep."""
    level = archive["folder_level"]
    parts = member.split("/")
    return parts[level - 1] if len(parts) > level else None


def image_folders(disk_root=DISK_ROOT, dataset=None):
    """Per experiment folder: image count and the match keys in its names.

    Lists the zip directories only, nothing is extracted.
    """
    ds = _dataset(dataset)
    extensions, skipped = _extensions(ds), _skipped(ds)
    folders = {}
    for archive in ds.images["archives"]:
        zip_name, family = archive["zip"], archive.get("group")
        path = os.path.join(disk_root, zip_name)
        if not os.path.exists(path):
            continue
        with zipfile.ZipFile(path) as zf:
            for member in zf.namelist():
                if not member.lower().endswith(extensions):
                    continue
                parsed = parse_filename(ds, os.path.basename(member))
                folder = _experiment_folder(archive, member)
                if not parsed or not folder or (zip_name, folder) in skipped:
                    continue
                entry = folders.setdefault((zip_name, folder), {
                    "zip": zip_name, "family": family, "folder": folder,
                    "images": 0, "pairs": collections.Counter(),
                })
                entry["images"] += 1
                entry["pairs"][_image_key(ds, parsed)] += 1
    return list(folders.values())


def propose_aliases(wells, folders, dataset=None):
    """Compare image folders with metadata experiments. Changes nothing.

    Each result has a ``kind``: ``exact`` (same after normalising), ``alias``
    (in the config's aliases), ``proposed`` (same lab identifier within the same
    workbook family, for a human to confirm) or ``none``. ``matched`` is how many
    images have match keys that exist in that experiment, the evidence for or
    against the link. ``first_values`` lists the folder's values of the first key.
    """
    ds = _dataset(dataset)
    aliases = _match_rules(ds).get("aliases") or {}
    separator = ds.metadata.get("workbook_group_separator")
    experiments = {}
    for well in wells:
        group = _group(ds, well)
        if not group:
            continue
        workbook = well["source_workbook"]
        family = workbook.split(separator)[0] if separator else workbook
        entry = experiments.setdefault(group, {"family": family, "pairs": set()})
        entry["pairs"].update(_sample_keys(ds, well))
    by_key = {_name_key(ds, name): name for name in experiments}

    results = []
    used = set()
    for folder in sorted(folders, key=lambda f: (f["zip"], f["folder"])):
        name = by_key.get(_name_key(ds, folder["folder"]))
        kind = "exact" if name else "none"
        if not name and aliases.get(folder["folder"]) in experiments:
            name, kind = aliases[folder["folder"]], "alias"
        if not name and ds.tokens_re is not None:
            tokens = experiment_tokens(folder["folder"], ds.tokens_re)
            candidates = [
                e for e, info in experiments.items()
                if info["family"] == folder["family"]
                and tokens & experiment_tokens(e, ds.tokens_re)
            ]
            if len(candidates) == 1:
                name, kind = candidates[0], "proposed"
        matched = 0
        if name:
            used.add(name)
            pairs = experiments[name]["pairs"]
            matched = sum(c for p, c in folder["pairs"].items() if p in pairs)
        results.append({
            "zip": folder["zip"], "folder": folder["folder"], "experiment": name,
            "kind": kind, "images": folder["images"], "matched": matched,
            "first_values": sorted({p[0] for p in folder["pairs"] if p and p[0]}),
        })
    return results, sorted(set(experiments) - used)


def actor_id(cur, email):
    """User id for a CLI ``--as`` email; must be an admin or curator."""
    cur.execute(
        "SELECT u.id, r.role FROM auth.users u "
        "LEFT JOIN _fd.user_roles r ON r.user_id = u.id WHERE u.email = %s",
        (email,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"no user with email {email}")
    if row[1] not in ("admin", "curator"):
        raise ValueError(f"{email} has role {row[1]}, needs admin or curator")
    return str(row[0])


def write_wells(cur, data, owner_id):
    """Upsert wells and legends, with one audit row. Caller commits.

    Natural key is (dataset, source_workbook, source_sheet, source_row). An
    unchanged row is left alone, so a re-run neither duplicates nor touches
    ``updated_at``.
    """
    dataset = data["dataset"]
    casts = {
        "dataset": "text", "source_workbook": "text", "source_sheet": "text",
        "source_row": "integer", "fields": "jsonb", "props": "jsonb",
    }
    columns = list(casts)
    compared = [c for c in columns if c != "dataset" and not c.startswith("source_")]

    def value(well, column):
        if column == "dataset":
            return dataset
        if column in ("fields", "props"):
            return json.dumps(well[column])
        return well[column]

    rows = [(owner_id, *[value(w, c) for c in columns]) for w in data["wells"]]
    returned = execute_values(
        cur,
        f"INSERT INTO _fd.imagehub_wells (owner_id, {', '.join(columns)}) VALUES %s "
        "ON CONFLICT (dataset, source_workbook, source_sheet, source_row) DO UPDATE SET "
        f"{', '.join(f'{c} = EXCLUDED.{c}' for c in compared)}, updated_at = now() WHERE "
        f"({', '.join('_fd.imagehub_wells.' + c for c in compared)}) IS DISTINCT FROM "
        f"({', '.join('EXCLUDED.' + c for c in compared)}) "
        "RETURNING source_workbook, source_sheet, source_row, (xmax = 0)",
        rows,
        template="(%s, " + ", ".join(f"%s::{casts[c]}" for c in columns) + ")",
        page_size=500,
        fetch=True,
    )
    status = {(r[0], r[1], r[2]): "inserted" if r[3] else "updated" for r in returned}
    for legend in data["legends"]:
        cur.execute(
            "INSERT INTO _fd.imagehub_legends "
            "(owner_id, dataset, source_workbook, source_sheet, rows) "
            "VALUES (%s, %s, %s, %s, %s::jsonb) "
            "ON CONFLICT (dataset, source_workbook, source_sheet) DO UPDATE "
            "SET rows = EXCLUDED.rows, updated_at = now() "
            "WHERE _fd.imagehub_legends.rows IS DISTINCT FROM EXCLUDED.rows",
            (owner_id, dataset, legend["source_workbook"], legend["source_sheet"],
             json.dumps(legend["rows"])),
        )
    counts = collections.Counter(status.values())
    counts["unchanged"] = len(rows) - len(status)
    record("imagehub_wells", actor=owner_id, action="import", after={
        **counts,
        "dataset": dataset,
        "sources": sorted({w["source_workbook"] for w in data["wells"]}),
    })
    return status, counts


def long_report_columns(ds):
    """The fields that name a row in metadata_long.csv, and the fields listed per row:
    ``metadata.long_report``, or else the required fields and all other fields."""
    md = ds.metadata
    report = md.get("long_report") or {}
    key = report.get("key") or list(md["required"])
    if "values" in report:
        return key, report["values"]
    names = []
    for name, spec in md["fields"].items():
        names.append(name)
        if "header_regex" in spec:
            names.append(spec.get("unit_field", f"{name}_unit"))
    return key, [n for n in names if n not in key]


def write_reports(report_dir, data, status, dataset=None):
    """Write the per-row report and the long-format export of imported rows."""
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "metadata_report.csv")
    with open(report_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["source_workbook", "source_sheet", "source_row", "status"])
        writer.writerows(data["report"])
        for w in data["wells"]:
            key = (w["source_workbook"], w["source_sheet"], w["source_row"])
            writer.writerow([*key, status.get(key, "unchanged")])
    key, values = long_report_columns(dataset or config.get(data["dataset"]))
    long_path = os.path.join(report_dir, "metadata_long.csv")
    with open(long_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["source_workbook", "source_sheet", "source_row", *key, "column", "value"])
        for w in data["wells"]:
            prefix = (w["source_workbook"], w["source_sheet"], w["source_row"], *(w.get(k) for k in key))
            for column in values:
                writer.writerow([*prefix, column, w.get(column)])
            for column, value in w["props"].items():
                writer.writerow([*prefix, column, value])
    return report_path, long_path


# ── Image catalog ─────────────────────────────────────────────────────────────

def _image_row(ds, zip_name, member, size, folder):
    """Catalog fields for one image member, or None if its name has another form."""
    name = member.rsplit("/", 1)[-1]
    parsed = parse_filename(ds, name)
    if parsed is None:
        return None
    return {
        **parsed,
        "dataset": ds.id,
        "fields": _present(parsed),
        "folder": folder,
        "source_zip": zip_name,
        "source_member": member,
        "original_name": name,
        "mime": mime_type(name),
        "size_bytes": size,
    }


def _is_junk(member):
    base = member.rsplit("/", 1)[-1]
    return member.endswith("/") or "__MACOSX/" in member or base.startswith(".")


def walk_images(disk_root=None, dataset=None):
    """List every image on the disk. Nothing is extracted to disk.

    Returns ``{"images", "unparsed", "nested", "missing_zips"}``. Copies listed in
    the config's ``images.skip`` are left out.
    """
    disk_root = disk_root or DISK_ROOT
    ds = _dataset(dataset)
    extensions, skipped = _extensions(ds), _skipped(ds)
    annotation = ds.images.get("annotation_archive") or {}
    annotation_zip = annotation.get("zip")
    # Without a prefix no nested zip is opened: all of them go to the report.
    nested_prefix = annotation.get("nested_prefix")
    nested_groups = annotation.get("nested_groups") or {}
    archives = {a["zip"]: a for a in ds.images["archives"]}
    images, unparsed, nested, missing = [], [], [], []
    for zip_name in (*archives, *([annotation_zip] if annotation_zip else [])):
        path = os.path.join(disk_root, zip_name)
        if not os.path.exists(path):
            missing.append(zip_name)
            continue
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                member = info.filename
                if _is_junk(member):
                    continue
                lower = member.lower()
                if lower.endswith(NESTED_ARCHIVES):
                    if zip_name == annotation_zip and lower.endswith(".zip") \
                            and nested_prefix and member.startswith(nested_prefix):
                        with zipfile.ZipFile(io.BytesIO(zf.read(info))) as inner:
                            for item in inner.infolist():
                                inner_member = item.filename
                                if _is_junk(inner_member) or not inner_member.lower().endswith(extensions):
                                    continue
                                full = f"{member}{NESTED_SEPARATOR}{inner_member}"
                                row = _image_row(ds, zip_name, full, item.file_size, None)
                                if row:
                                    row["experiment_hint"] = nested_groups.get(
                                        member.rsplit("/", 1)[-1]
                                    )
                                (images.append(row) if row else unparsed.append((zip_name, full)))
                    else:
                        nested.append((zip_name, member, info.file_size))
                    continue
                if not lower.endswith(extensions):
                    continue
                folder = None if zip_name == annotation_zip else _experiment_folder(archives[zip_name], member)
                if (zip_name, folder) in skipped:
                    continue
                row = _image_row(ds, zip_name, member, info.file_size, folder)
                (images.append(row) if row else unparsed.append((zip_name, member)))
    return {"images": images, "unparsed": unparsed, "nested": nested, "missing_zips": missing}


def load_match_index(cur, dataset=None):
    """Sample rows as lookups by their match keys: within their group (experiment)
    and, for images without a known group, over the whole dataset. Also returns
    the group of each row. Only the dataset's own rows are read."""
    ds = _dataset(dataset)
    rules = _match_rules(ds)
    infer = rules.get("infer_single") or {}
    infer_sample = next(
        (k["sample"] for k in rules.get("keys") or () if k["image"] == infer.get("field")), None,
    )
    cur.execute("SELECT id, fields FROM _fd.imagehub_wells WHERE dataset = %s", (ds.id,))
    by_group = collections.defaultdict(set)
    by_keys = collections.defaultdict(set)
    group_of = {}
    values_of = collections.defaultdict(set)
    for well_id, fields in cur.fetchall():
        well_id, group = str(well_id), _group(ds, fields)
        group_of[well_id] = group
        if infer_sample:
            value = fields.get(infer_sample)
            values_of[group].update(v for v in (value if isinstance(value, list) else [value])
                                    if v is not None)
        for key in _sample_keys(ds, fields):
            by_group[(group, *key)].add(well_id)
            by_keys[key].add(well_id)
    names = {_name_key(ds, g): g for g in group_of.values() if g}
    return {"by_group": by_group, "by_keys": by_keys, "group_of": group_of,
            "values_of": values_of, "names": names}


def match_image(image, index, dataset=None):
    """Link an image to a sample row (well) by the dataset's match keys. Never
    picks one of several candidates.

    Fills ``experiment`` (the group), ``well_id``, ``match_status`` and
    ``match_reason``; ``candidates`` holds the rows of an ambiguous match.
    """
    ds = _dataset(dataset)
    rules = _match_rules(ds)
    keys = rules.get("keys") or ()
    grouped = "group_field" in rules
    aliases = rules.get("aliases") or {}
    folder = image["folder"]
    experiment = image.get("experiment_hint")
    if grouped and folder:
        experiment = (
            index["names"].get(_name_key(ds, folder))
            or (aliases.get(folder)
                if aliases.get(folder) in index["names"].values() else None)
        )
    values = dict(zip((k["image"] for k in keys), _image_key(ds, image)))
    infer = rules.get("infer_single") or {}
    inferred = None
    if infer and not values[infer["field"]] and experiment in infer["groups"] \
            and len(index["values_of"].get(experiment, ())) == 1:
        inferred = infer["field"]
        key = next(k for k in keys if k["image"] == inferred)
        values[inferred] = _match_value(key, next(iter(index["values_of"][experiment])))
    key = tuple(values.values())
    missing = next((name for name, value in values.items() if not value), None)
    candidates = set()
    if not keys:
        reason = "no_match_rules"
    elif missing:
        reason = f"no_{missing}_in_name"
    elif grouped and folder and not experiment:
        reason = "no_metadata_for_experiment"
    elif experiment:
        candidates = index["by_group"].get((experiment, *key), set())
        reason = "not_in_experiment"
    else:
        candidates = index["by_keys"].get(key, set())
        reason = "not_in_metadata"

    if len(candidates) == 1:
        well_id = next(iter(candidates))
        status = "inferred" if inferred else "matched"
        reason = f"{inferred}_inferred_from_experiment" if inferred else None
        experiment = index["group_of"][well_id]
    elif candidates:
        well_id, status = None, "ambiguous"
        reason = "several_wells_in_experiment" if experiment else "several_experiments"
    else:
        well_id, status = None, "unmatched"
    # An inferred value is stored only when it led to a well.
    found = {inferred: values[inferred]} if status == "inferred" else {}
    return {
        **image,
        **found,
        **({"fields": {**image["fields"], **found}} if found and "fields" in image else {}),
        "experiment": experiment or folder,
        "well_id": well_id,
        "match_status": status,
        "match_reason": reason,
        "candidates": candidates if status == "ambiguous" else set(),
    }


def _sql_names(names):
    """A SQL text[] literal of config field names (checked: ``[a-z][a-z0-9_]*``)."""
    checked = sorted(names)
    for name in checked:
        if not config._FIELD_RE.match(name):
            raise ValueError(f"not a field name: {name!r}")
    return "ARRAY[" + ", ".join(f"'{n}'" for n in checked) + "]::text[]"


def write_images(cur, images, owner_id, keep=()):
    """Upsert catalog rows, with one audit row. Caller commits.

    Natural key is (dataset, source_zip, source_member). ``storage_path`` and
    ``preview_path`` are not in the update, so a re-run keeps uploads.

    ``keep``: the dataset's extra field names. Their values in ``fields`` are not
    from the file name, so a re-run carries them over, and a row that differs only
    in them is not updated (it counts as unchanged). Every other key of ``fields``
    is replaced by the parsed file name, as before.
    """
    casts = {
        "dataset": "text", "source_zip": "text", "source_member": "text",
        "well_id": "uuid", "match_status": "text", "fields": "jsonb", "experiment": "text",
        "mime": "text", "size_bytes": "bigint", "original_name": "text",
    }
    columns = list(casts)
    compared = [c for c in columns if c not in ("dataset", "source_zip", "source_member")]

    def value(image, column):
        if column == "fields":
            return json.dumps(image["fields"])
        return image[column]

    kept = _sql_names(keep)
    current = {c: f"_fd.imagehub_images.{c}" for c in compared}
    current["fields"] = f"(_fd.imagehub_images.fields - {kept})"
    assign = {c: f"EXCLUDED.{c}" for c in compared}
    assign["fields"] = (
        "EXCLUDED.fields || (SELECT COALESCE(jsonb_object_agg(e.key, e.value), '{}'::jsonb) "
        "FROM jsonb_each(_fd.imagehub_images.fields) AS e "
        f"WHERE e.key = ANY({kept}))"
    )
    returned = execute_values(
        cur,
        f"INSERT INTO _fd.imagehub_images (owner_id, {', '.join(columns)}) "
        "VALUES %s ON CONFLICT (dataset, source_zip, source_member) DO UPDATE SET "
        f"{', '.join(f'{c} = {assign[c]}' for c in compared)}, updated_at = now() WHERE "
        f"({', '.join(current[c] for c in compared)}) IS DISTINCT FROM "
        f"({', '.join('EXCLUDED.' + c for c in compared)}) "
        "RETURNING source_zip, source_member, (xmax = 0)",
        [(owner_id, *[value(i, c) for c in columns]) for i in images],
        template="(%s, " + ", ".join(f"%s::{casts[c]}" for c in columns) + ")",
        page_size=1000,
        fetch=True,
    )
    status = {(r[0], r[1]): "inserted" if r[2] else "updated" for r in returned}
    counts = collections.Counter(status.values())
    counts["unchanged"] = len(images) - len(status)
    record("imagehub_images", actor=owner_id, action="catalog", after={
        **counts,
        **collections.Counter(i["match_status"] for i in images),
    })
    return status, counts


def write_catalog_reports(report_dir, walked, images, status, cur, dataset=None):
    """Per-image report, unmatched summary, wells without images, other files."""
    ds = _dataset(dataset)
    os.makedirs(report_dir, exist_ok=True)
    paths = {}

    def table(name, header, rows):
        paths[name] = os.path.join(report_dir, name)
        with open(paths[name], "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerows(rows)

    rules = _match_rules(ds)
    keys = [k["image"] for k in rules.get("keys") or ()]
    table("catalog_report.csv",
          ["source_zip", "source_member", "status", "match_status", "match_reason",
           "experiment", *keys],
          ((i["source_zip"], i["source_member"],
            status.get((i["source_zip"], i["source_member"]), "unchanged"),
            i["match_status"], i["match_reason"], i["experiment"], *(i.get(k) for k in keys))
           for i in images))
    table("catalog_not_parsed.csv", ["source_zip", "source_member"], walked["unparsed"])
    table("catalog_nested_not_opened.csv", ["source_zip", "source_member", "size_bytes"],
          walked["nested"])

    linked = {i["well_id"] for i in images if i["well_id"]}
    candidates = set().union(*(i["candidates"] for i in images)) if images else set()
    cur.execute(
        "SELECT id, source_workbook, source_sheet, source_row, fields "
        "FROM _fd.imagehub_wells WHERE dataset = %s ORDER BY 2, 3, 4",
        (ds.id,),
    )

    def shown(fields, key):
        # The row's own field of the image's name (a raw VID) if it has one,
        # else the field it is matched on.
        value = fields.get(key["image"], fields.get(key["sample"]))
        return ";".join(value) if isinstance(value, list) else value

    without = []
    for well_id, workbook, sheet, row_number, fields in cur.fetchall():
        well_id = str(well_id)
        if well_id not in linked:
            state = "ambiguous_images_only" if well_id in candidates else "no_images"
            without.append((workbook, sheet, row_number, _group(ds, fields),
                            *(shown(fields, k) for k in rules.get("keys") or ()), state))
    table("wells_without_images.csv",
          ["source_workbook", "source_sheet", "source_row", "experiment", *keys, "state"],
          without)
    return paths, without


# ── Upload ────────────────────────────────────────────────────────────────────

def read_member(source_zip, source_member, disk_root=None):
    """Bytes of an image inside a zip, or inside a nested zip."""
    disk_root = disk_root or DISK_ROOT
    with zipfile.ZipFile(os.path.join(disk_root, source_zip)) as zf:
        if NESTED_SEPARATOR not in source_member:
            return zf.read(source_member)
        outer, inner = source_member.split(NESTED_SEPARATOR, 1)
        with zipfile.ZipFile(io.BytesIO(zf.read(outer))) as nested:
            return nested.read(inner)


def make_preview(content):
    """Same-size JPEG of an 8-bit image, for browsers (they cannot show TIFF).

    Returns None for other pixel formats: stretching them would need a contrast
    choice that should not be made silently. Keeping the size means VIA regions
    line up with the preview.
    """
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.mode not in ("L", "RGB"):
                return None
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=90)
    except (UnidentifiedImageError, OSError):
        return None
    return out.getvalue()


def upload_image(cur, image, disk_root=None):
    """Upload one catalog row (a dict with id, names and paths). Caller commits.

    Returns ``"skipped"`` if it is already in the bucket, else ``"uploaded"``.
    Keys contain the image id, so retrying after a failure overwrites the same
    objects instead of leaving strays.
    """
    if image["storage_path"]:
        return "skipped"
    content = read_member(image["source_zip"], image["source_member"], disk_root)
    key = storage_key(image["dataset"], image["experiment"], image["id"], image["original_name"])
    storage_path = upload_stream(BUCKET, key, content, image["mime"], upsert=True)
    preview_path = None
    if image["mime"] == "image/tiff":
        preview = make_preview(content)
        if preview:
            preview_path = upload_stream(BUCKET, key + ".preview.jpg", preview, "image/jpeg", upsert=True)
    cur.execute(
        "UPDATE _fd.imagehub_images SET storage_path = %s, preview_path = %s, "
        "size_bytes = %s, updated_at = now() WHERE id = %s",
        (storage_path, preview_path, len(content), image["id"]),
    )
    return "uploaded"


_UPLOAD_COLUMNS = (
    "id", "dataset", "experiment", "source_zip", "source_member", "original_name",
    "mime", "storage_path",
)


def select_images(cur, *, image_ids=None, name=None, experiment=None, fields=None,
                  source_zip=None, annotated=False, limit=50, dataset=None):
    """Catalog rows for a selection. At least one filter is required; ``dataset``
    (an id) limits it to one dataset but does not count as a filter. ``fields`` are
    image fields from the file name, ``{name: value}``, compared as stored."""
    filters = {
        "id = ANY(%s::uuid[])": image_ids,
        "original_name = %s": name,
        "experiment = %s": experiment,
        "fields @> %s::jsonb": json.dumps(fields) if fields else None,
        "source_zip = %s": source_zip,
    }
    active = {clause: value for clause, value in filters.items() if value}
    clauses = list(active)
    scope = {"dataset = %s": dataset} if dataset else {}
    if annotated:
        clauses.append(
            "EXISTS (SELECT 1 FROM _fd.imagehub_annotations a "
            "WHERE a.image_id = _fd.imagehub_images.id)"
        )
    if not clauses:
        raise ValueError("select at least one filter")
    cur.execute(
        f"SELECT {', '.join(_UPLOAD_COLUMNS)} FROM _fd.imagehub_images "
        f"WHERE {' AND '.join([*scope, *clauses])} ORDER BY source_zip, source_member LIMIT %s",
        (*scope.values(), *active.values(), limit),
    )
    return [
        {**dict(zip(_UPLOAD_COLUMNS, row)), "id": str(row[0])} for row in cur.fetchall()
    ]


def upload_via_json(cur, source_zip, member, disk_root=None, dataset=None):
    """Put the original VIA file in the bucket, unchanged. Caller commits.

    Every annotation from this file then points to it. Returns the storage path.
    """
    ds = _dataset(dataset)
    content = read_member(source_zip, member, disk_root)
    source_file = f"{source_zip}{NESTED_SEPARATOR}{member}"
    digest = hashlib.sha1(source_file.encode("utf-8")).hexdigest()[:12]
    key = storage_key(ds.id, "via", digest, member.rsplit("/", 1)[-1])
    storage_path = upload_stream(BUCKET, key, content, "application/json", upsert=True)
    cur.execute(
        "UPDATE _fd.imagehub_annotations SET source_storage_path = %s, updated_at = now() "
        "WHERE source_file = %s AND source_storage_path IS DISTINCT FROM %s",
        (storage_path, source_file, storage_path),
    )
    return storage_path


def json_blobs_without_annotations(cur, storage_paths):
    """Those VIA files in the bucket that no annotation points to any more."""
    paths = {path for path in storage_paths if path}
    if not paths:
        return []
    cur.execute(
        "SELECT DISTINCT source_storage_path FROM _fd.imagehub_annotations "
        "WHERE source_storage_path = ANY(%s)",
        (list(paths),),
    )
    return sorted(paths - {row[0] for row in cur.fetchall()})


def delete_blobs(*storage_paths):
    """Remove blobs; empty paths are ignored. Returns True if none failed."""
    return all([delete_object(path) for path in storage_paths if path])


# ── VIA annotations ───────────────────────────────────────────────────────────

def _via_image(cur, dataset_id, filename, size, source_zip, directory):
    """Find the image a VIA entry refers to, in one dataset. Prefers the json's
    own folder.

    Returns ``(image id or None, reason or None)``.
    """
    cur.execute(
        "SELECT id, source_member, size_bytes FROM _fd.imagehub_images "
        "WHERE dataset = %s AND original_name = %s AND source_zip = %s",
        (dataset_id, filename, source_zip),
    )
    rows = cur.fetchall()
    same_folder = [r for r in rows if r[1].rsplit("/", 1)[0] == directory]
    if len(same_folder) == 1:
        rows = same_folder
    if not rows:
        return None, "no_image_with_this_name"
    if len(rows) > 1:
        return None, "several_images_with_this_name"
    if size is not None and rows[0][2] is not None and int(size) != rows[0][2]:
        return None, "size_differs_from_image"
    return str(rows[0][0]), None


def _annotator(ds, member):
    """Annotator label from a VIA file name, by the config's pattern."""
    rules = ds.annotations
    return annotator_label(member, ds.annotator_re, rules.get("unknown_label", UNKNOWN_ANNOTATOR))


def import_via(cur, source_zip, member, owner_id, only=None, disk_root=None, dataset=None):
    """Import one VIA json from a zip, with one audit row. Caller commits.

    The label comes from the file name suffix. ``only`` limits the import to one image file name. Returns report rows
    ``(file name, status)``. Re-running changes nothing unless the regions differ.
    """
    ds = _dataset(dataset)
    nested_annotators = ds.annotations.get("nested_annotators") or {}
    nested_folders = ds.annotations.get("nested_image_folders") or {}
    data = json.loads(read_member(source_zip, member, disk_root))
    source_file = f"{source_zip}{NESTED_SEPARATOR}{member}"
    label = _annotator(ds, member)
    directory = member.rsplit("/", 1)[0]
    if NESTED_SEPARATOR in member:
        outer = member.split(NESTED_SEPARATOR, 1)[0]
        outer_folder, outer_name = outer.rsplit("/", 1)
        label = nested_annotators.get(outer_name, label)
        if outer_name in nested_folders:
            directory = f"{outer_folder}/{nested_folders[outer_name]}"
    report = []
    for entry in parse_via(data):
        if only and entry["filename"] != only:
            continue
        image_id, reason = _via_image(cur, ds.id, entry["filename"], entry["size"], source_zip, directory)
        if not image_id:
            report.append((entry["filename"], reason))
            continue
        cur.execute(
            "INSERT INTO _fd.imagehub_annotations "
            "(owner_id, image_id, annotator_label, source, regions, source_file) "
            "VALUES (%s, %s, %s, 'via', %s::jsonb, %s) "
            "ON CONFLICT (image_id, annotator_label, source_file) DO UPDATE "
            "SET regions = EXCLUDED.regions, updated_at = now() "
            "WHERE _fd.imagehub_annotations.regions IS DISTINCT FROM EXCLUDED.regions "
            "RETURNING (xmax = 0)",
            (owner_id, image_id, label, json.dumps(entry["regions"]), source_file),
        )
        returned = cur.fetchone()
        status = "unchanged" if returned is None else "inserted" if returned[0] else "updated"
        report.append((entry["filename"], status))
    counts = collections.Counter(status for _, status in report)
    record("imagehub_annotations", actor=owner_id, action="import", after={
        **counts, "source_file": source_file, "annotator_label": label,
    })
    return report
