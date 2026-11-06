"""Export: one zip from a filter, for people without database access.

Holds the selected images, their VIA json, metadata.csv, README.txt and, when
needed, MISSING.txt. A file that cannot be read is listed, never fatal.
"""
import csv
import datetime
import io
import json
import os
import re
import shutil
import uuid
import zipfile

import requests

from kernel.audit import record
from kernel.env import get as env_get
from kernel.storage import signed_url

from . import config, ingest
from .dashboard import MAX_BYTES, build_dashboard, make_thumbnail
from .helpers import (
    NO_DESCRIPTION,
    browser_url,
    export_value,
    image_filter,
    image_order,
    legend_descriptions,
    legend_key,
    ref_value,
    safe_name,
)
from .rules import apply_steps

EXPORT_DIR = "uploads/imagehub-exports"
MAX_IMAGES_REQUEST = 500
_SIGNED_URL_TTL = 300  # seconds, one download

# Columns every export row has, whatever the dataset. ``image`` and ``sample``
# are the fields of the image and of its sample row; the config picks from them.
_IMAGE_COLUMNS = (
    "id", "original_name", "experiment", "match_status", "source_zip", "source_member",
    "storage_path", "size_bytes", "fields",
)
_WELL_COLUMNS = ("source_workbook", "source_sheet", "source_row", "fields", "props")
NOTE_COLUMN = "well_note"
NOTE_DESCRIPTION = (
    "Free text found in a cell where a value belongs, as '<column>: <text>'. The text "
    "is moved here from that column and is otherwise as written in the sheet"
)
REGIONS_TOTAL = "regions_total"
DEFAULT_CONTENTS = {"group": "group", "sample": "sample row", "label": "label"}


class ExportError(Exception):
    """A selection that cannot be exported; the message is for the user."""


def export_path(export_id):
    return os.path.join(EXPORT_DIR, f"{export_id}.zip")


def select_export_images(cur, filters, dataset):
    """All images of one dataset for a filter, with their wells."""
    clauses, params = image_filter(filters, dataset)
    order, order_params = image_order(dataset)
    columns = [f"i.{c}" for c in _IMAGE_COLUMNS] + [f"w.{c}" for c in _WELL_COLUMNS]
    cur.execute(
        f"SELECT {', '.join(columns)} FROM _fd.imagehub_images i "
        f"LEFT JOIN _fd.imagehub_wells w ON w.id = i.well_id WHERE {' AND '.join(clauses)} "
        f"ORDER BY {order}",
        (*params, *order_params),
    )
    rows = []
    for row in cur.fetchall():
        image = dict(zip(_IMAGE_COLUMNS, row[:len(_IMAGE_COLUMNS)]))
        well = dict(zip(_WELL_COLUMNS, row[len(_IMAGE_COLUMNS):]))
        rows.append(export_row(image, well))
    return rows


def export_row(image, well):
    """One export row from an image and its sample row (empty without one)."""
    return {
        **{k: v for k, v in image.items() if k != "fields"},
        "id": str(image["id"]),
        "image": image.get("fields") or {},
        "sample": well.get("fields") or {},
        "props": well.get("props"),
        "source_workbook": well.get("source_workbook"),
        "source_sheet": well.get("source_sheet"),
        "source_row": well.get("source_row"),
    }


class _Reader:
    """Reads image bytes, keeping big zips open: opening one costs a second."""

    def __init__(self, disk_root):
        self.disk_root = disk_root
        self.zips = {}

    def close(self):
        for archive in self.zips.values():
            archive.close()

    def _from_disk(self, image):
        name = image["source_zip"]
        if name not in self.zips:
            path = os.path.join(self.disk_root, name)
            if not os.path.exists(path):
                raise FileNotFoundError("disk not connected")
            self.zips[name] = zipfile.ZipFile(path)
        member = image["source_member"]
        if ingest.NESTED_SEPARATOR not in member:
            return self.zips[name].read(member)
        outer, inner = member.split(ingest.NESTED_SEPARATOR, 1)
        with zipfile.ZipFile(io.BytesIO(self.zips[name].read(outer))) as nested:
            return nested.read(inner)

    @staticmethod
    def _from_bucket(image):
        # The signed URL is used from inside Docker, so it keeps its own host.
        signed = signed_url(image["storage_path"], _SIGNED_URL_TTL)
        url = browser_url(signed, signed, env_get("SUPABASE_KEY"))
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        return response.content

    def read(self, image):
        """Bytes of an image: the bucket if it is there, else the disk."""
        if image["storage_path"]:
            try:
                return self._from_bucket(image)
            except (requests.RequestException, TypeError):
                pass  # the disk may still have it
        return self._from_disk(image)


def _unique_path(path, used):
    """``path``, or ``path`` with _2, _3 before the extension if already used."""
    stem, extension = os.path.splitext(path)
    candidate, number = path, 1
    while candidate in used:
        number += 1
        candidate = f"{stem}_{number}{extension}"
    used.add(candidate)
    return candidate


def _via_files(cur, images):
    """VIA json per source file, holding only the selected images.

    Returns ``{path in the zip: VIA dict}``, per image its region count per annotator
    label (two files with one label are added up), and per image its annotations.
    """
    by_id = {image["id"]: image for image in images}
    cur.execute(
        "SELECT image_id, annotator_label, source_file, regions "
        "FROM _fd.imagehub_annotations WHERE image_id = ANY(%s::uuid[]) "
        "ORDER BY annotator_label, source_file",
        (list(by_id),),
    )
    grouped, counts, shapes = {}, {}, {}
    for image_id, label, source_file, regions in cur.fetchall():
        image = by_id[str(image_id)]
        entries = grouped.setdefault((label, source_file), {})
        size = image["size_bytes"]
        entries[f"{image['original_name']}{size}"] = {
            "filename": image["original_name"],
            "size": size,
            "regions": regions,
            "file_attributes": {},
        }
        per_label = counts.setdefault(image["id"], {})
        per_label[label] = per_label.get(label, 0) + len(regions)
        shapes.setdefault(image["id"], []).append({"label": label, "regions": regions})
    used, files = set(), {}
    for (label, source_file), entries in grouped.items():
        base = source_file.rsplit("/", 1)[-1]
        files[_unique_path(f"annotations/{label}_{base}", used)] = entries
    return files, counts, shapes


def _wells_without_images(cur, images, dataset):
    """Sample rows of the selected groups that no image in the catalog links to, by
    the dashboard's key columns. None when the config cannot say which rows those are."""
    board = dataset.dashboard
    group_field = (dataset.images.get("match") or {}).get("group_field")
    sources = board.get("sample_fields") or {}
    if not group_field or not sources or set(sources) != set(board.get("key") or ()):
        return None
    groups = sorted({i["experiment"] for i in images if i["experiment"]})
    cur.execute(
        "SELECT w.fields FROM _fd.imagehub_wells w "
        "WHERE w.dataset = %s AND w.fields ->> %s = ANY(%s) AND NOT EXISTS "
        "(SELECT 1 FROM _fd.imagehub_images i WHERE i.well_id = w.id)",
        (dataset.id, group_field, groups),
    )
    rows = []
    for (fields,) in cur.fetchall():
        record = {"group": fields.get(group_field), "image": {}, "sample": fields}
        row = {}
        for name in board["key"]:
            value = ref_value(sources[name], record)
            row[name] = ";".join(map(str, value)) if isinstance(value, list) else value
        rows.append(row)
    return sorted(rows, key=lambda r: tuple("" if r[n] is None else str(r[n]) for n in board["key"]))


def dashboard_layout(dataset):
    """What the dashboard page needs to know of the dataset: its dashboard section,
    plus the words the README uses for a group and a sample row."""
    contents = {"group": "group", "sample": "sample row", **(dataset.export.get("contents") or {})}
    # Lists of preferences may name sheet columns: excluded ones are left out of the page.
    excluded = config.excluded_names(dataset.export)
    layout = {
        key: [v for v in value if v.strip().casefold() not in excluded]
        if key in _PREFERENCE_LISTS else value
        for key, value in dataset.dashboard.items()
    }
    return {**layout, "words": {"group": contents["group"], "sample": contents["sample"]}}


_PREFERENCE_LISTS = ("not_measured", "not_grouped", "colour_by", "compare_by", "values")


def _value(ref, row):
    if ref in config.BUILTIN_COLUMNS:
        return row.get(ref)
    return ref_value(ref, {"group": row.get("experiment"), "image": row["image"],
                           "sample": row["sample"]})


def column_value(column, row):
    """A config column's value for one row: its field, then ``steps``, ``divide``
    and ``round``; lists are joined. ``only_if`` leaves it empty without that field."""
    if "only_if" in column and _value(column["only_if"], row) in (None, "", []):
        return ""
    value = _value(column.get("from", column["name"]), row)
    if "steps" in column:
        value = apply_steps(value, column["steps"])
    if "divide" in column:
        if value is None:
            return ""
        value = value / column["divide"]
        if "round" in column:
            value = round(value, column["round"])
    if isinstance(value, list):
        value = column.get("join", ";").join(str(v) for v in value)
    return value


def _columns(dataset):
    """``[(section, columns)]`` of the config's column sections, in file order,
    without the columns in ``export.exclude``."""
    return [(s["title"], _kept(s["columns"], dataset)) for s in dataset.export["sections"]
            if "columns" in s and _kept(s["columns"], dataset)]


def _kept(columns, dataset):
    excluded = config.excluded_names(dataset.export)
    return [c for c in columns if c["name"].strip().casefold() not in excluded]


def _sheet_group(sheet, header):
    for group in sheet.get("groups") or ():
        if group.get("exclude") and re.search(group["exclude"], header):
            continue
        if re.match(group["match"], header.strip(), re.IGNORECASE):
            return group["title"]
    return sheet["other"]


def _sheet_columns(images, reserved, dataset):
    """Sheet-specific columns: ``{group title: {header: column}}``, in config order.

    Sorted by name so a column keeps its place between exports. Headers in the
    config's ``merge`` share a column, unless both occur in one sheet: those are
    two measurements and stay apart. A header equal to one of ours gets a suffix,
    so the configured column does not lose out.
    """
    sheet = dataset.export.get("sheet_columns")
    if not sheet:
        return {}
    merges = sheet.get("merge") or {}
    # Excluded headers, and headers merged into an excluded column, never get a column.
    excluded = config.excluded_names(dataset.export)
    left_out = lambda h: h.strip().casefold() in excluded or merges.get(h, "").strip().casefold() in excluded
    sheets = {}
    for image in images:
        for key in image["props"] or {}:
            if not left_out(key):
                sheets.setdefault(key, set()).add((image.get("source_workbook"), image.get("source_sheet")))

    def column_of(header):
        target = merges.get(header)
        name = target if target and not sheets[header] & sheets.get(target, set()) else header
        return f"{name} (workbook)" if name in reserved else name

    groups = {g["title"]: {} for g in sheet.get("groups") or ()}
    groups[sheet["other"]] = {}
    for header in sorted(sheets, key=lambda h: (column_of(h).casefold(), h)):
        groups[_sheet_group(sheet, header)][header] = column_of(header)
    return groups


def _is_note(notes, header, value):
    """A sentence in a cell where a value belongs: text of ``min_words`` words or more."""
    if not notes or header.strip() in (notes.get("except") or ()):
        return False
    return isinstance(value, str) and len(value.split()) >= notes["min_words"]


def _metadata_csv(images, statuses, paths, counts, dataset):
    """Returns the csv text, the sheet column groups and the region columns."""
    labels = sorted({label for per_label in counts.values() for label in per_label})
    region_columns = {f"regions_{label}": label for label in labels}
    notes = dataset.export.get("notes")
    configured = [c for _, columns in _columns(dataset) for c in columns]
    reserved = {c["name"] for c in configured} | {*region_columns, REGIONS_TOTAL}
    if notes:
        reserved.add(NOTE_COLUMN)
    groups = _sheet_columns(images, reserved, dataset)
    order = []
    for section in dataset.export["sections"]:
        if "columns" in section:
            order += [c["name"] for c in _kept(section["columns"], dataset)]
        elif "annotations" in section:
            order += [*region_columns, REGIONS_TOTAL]
        elif "sheet_columns" in section:
            order += [column for group in groups.values() for column in group.values()]
        elif "notes" in section:
            order.append(NOTE_COLUMN)
    # Merged headers share a column, so each name goes in once.
    fieldnames = list(dict.fromkeys(order))
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames)
    writer.writeheader()
    for image in images:
        per_label = counts.get(image["id"], {})
        row_data = {**image, "image_file": paths.get(image["id"], ""),
                    "file_status": statuses[image["id"]]}
        row = {c["name"]: column_value(c, row_data) for c in configured}
        row[REGIONS_TOTAL] = sum(per_label.values()) if per_label else ""
        for column, label in region_columns.items():
            row[column] = per_label.get(label, "")
        found = []
        for group in groups.values():
            for header, column in group.items():
                value = (image["props"] or {}).get(header)
                if _is_note(notes, header, value):
                    found.append(f"{header.strip()}: {value}")
                    value = None
                # A merged column must not be blanked by the header this well lacks.
                if value is not None:
                    row[column] = export_value(value)
        if notes:
            row[NOTE_COLUMN] = "; ".join(found)
        writer.writerow({k: v for k, v in row.items() if k in fieldnames})
    return out.getvalue(), groups, list(region_columns)


def _descriptions(cur, dataset):
    """Column descriptions from every Legend sheet of the dataset: sheets share
    their headers."""
    cur.execute("SELECT rows FROM _fd.imagehub_legends WHERE dataset = %s ORDER BY source_workbook",
                (dataset.id,))
    descriptions = {}
    for (rows,) in cur.fetchall():
        for key, text in legend_descriptions(rows).items():
            descriptions.setdefault(key, text)
    return descriptions


def _readme(filters, images, included, missing, groups, region_columns, descriptions, dataset):
    ex = dataset.export
    words = {**DEFAULT_CONTENTS, **(ex.get("contents") or {})}
    lines = [
        ex.get("name", f"{dataset.title} export"),
        f"Created: {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC",
        f"Filter: {json.dumps(filters, ensure_ascii=False, sort_keys=True)}",
        f"Images selected: {len(images)}; included: {included}; missing: {len(missing)}",
        "",
        "Contents",
        f"  images/        original files, unchanged, per {words['group']}",
        "  annotations/   VIA json per annotator, only for the selected images.",
        f"                 File names start with the annotator's {words['label']}, or "
        f"'{dataset.annotations.get('unknown_label', 'unknown')}'.",
        f"  metadata.csv   one row per image, with the metadata of its {words['sample']}",
        "  dashboard.html charts and thumbnails. Opens by double-click, works offline",
    ]
    if missing:
        lines.append("  MISSING.txt    selected images that could not be read")

    def section(title, columns):
        lines.extend(["", title])
        lines.extend(f"  {column}: {text}" for column, text in columns.items())

    lines += ["", "Columns in metadata.csv, in file order"]
    sheet = ex.get("sheet_columns") or {}
    for part in ex["sections"]:
        if "columns" in part:
            if _kept(part["columns"], dataset):
                section(part["title"], {c["name"]: c["description"] for c in _kept(part["columns"], dataset)})
        elif "annotations" in part:
            section(part["annotations"], {
                **{c: f"Number of regions from annotator {c[len('regions_'):]}; 0 means annotated, "
                      "no regions found; empty means not annotated by them" for c in region_columns},
                REGIONS_TOTAL: "Sum over annotators. Their regions can overlap, so this is not a "
                               "number of distinct clusters. Empty if the image has no annotation",
            })
        elif "sheet_columns" in part:
            if sheet.get("intro"):
                lines += ["", *sheet["intro"]]
            for title, group in groups.items():
                section(title, {
                    column: descriptions.get(legend_key(header), NO_DESCRIPTION)
                    for header, column in group.items()
                })
        elif "notes" in part:
            section(part["notes"], {NOTE_COLUMN: ex["notes"].get("description", NOTE_DESCRIPTION)})
    return "\n".join(lines) + "\n"


def _missing_text(missing):
    lines = ["original_name\treason\tsource_zip\tsource_member"]
    lines += [
        f"{m['original_name']}\t{m['reason']}\t{m['source_zip']}\t{m['source_member']}"
        for m in missing
    ]
    return "\n".join(lines) + "\n"


def build_export(cur, filters, owner_id, *, max_images):
    """Write the zip and its record, with one audit row. Caller commits.

    Raises ExportError for an empty selection, one over ``max_images``, or too
    little free space. Images are written one at a time, so memory stays small.
    """
    try:
        dataset = config.get(filters.get("dataset") or None)
    except config.ConfigError as exc:
        raise ExportError(str(exc)) from None
    images = select_export_images(cur, filters, dataset)
    if not images:
        raise ExportError("no images match this filter")
    total = sum(image["size_bytes"] or 0 for image in images)
    if len(images) > max_images:
        raise ExportError(
            f"{len(images)} images (about {total / 1e9:.1f} GB) is over the limit of "
            f"{max_images}. Narrow the filter, or use the CLI with --max-images."
        )
    os.makedirs(EXPORT_DIR, exist_ok=True)
    free = shutil.disk_usage(EXPORT_DIR).free
    if free < total * 1.1:
        raise ExportError(
            f"needs about {total / 1e9:.1f} GB, only {free / 1e9:.1f} GB is free"
        )

    export_id = str(uuid.uuid4())
    final_path = export_path(export_id)
    temp_path = f"{final_path}.tmp"
    reader = _Reader(ingest.DISK_ROOT)
    statuses, paths, missing = {}, {}, []
    thumbnails, thumbnail_bytes = {}, 0
    used = set()
    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for image in images:
                try:
                    content = reader.read(image)
                except (OSError, KeyError, zipfile.BadZipFile) as exc:
                    reason = str(exc) if isinstance(exc, FileNotFoundError) else "could not be read"
                    statuses[image["id"]] = reason
                    missing.append({
                        "id": image["id"],
                        "original_name": image["original_name"],
                        "source_zip": image["source_zip"],
                        "source_member": image["source_member"],
                        "reason": reason,
                    })
                    continue
                folder = safe_name(image["experiment"])
                path = _unique_path(f"images/{folder}/{image['original_name']}", used)
                # Images are compressed already, so they are stored as they are.
                archive.writestr(path, content, compress_type=zipfile.ZIP_STORED)
                statuses[image["id"]] = "included"
                paths[image["id"]] = path
                # Past the limit they would be dropped anyway: stop making them.
                if thumbnail_bytes <= MAX_BYTES:
                    thumbnail = make_thumbnail(content)
                    if thumbnail:
                        thumbnails[path] = thumbnail
                        thumbnail_bytes += len(thumbnail["src"])

            via_files, counts, shapes = _via_files(cur, images)
            for path, entries in via_files.items():
                archive.writestr(path, json.dumps(entries, ensure_ascii=False, indent=1))
            metadata, groups, region_columns = _metadata_csv(images, statuses, paths, counts, dataset)
            archive.writestr("metadata.csv", metadata)
            archive.writestr("README.txt", _readme(
                filters, images, len(paths), missing, groups, region_columns,
                _descriptions(cur, dataset), dataset,
            ))
            html, dashboard_note = build_dashboard(
                metadata, thumbnails,
                {paths[i]: value for i, value in shapes.items() if i in paths},
                _wells_without_images(cur, images, dataset),
                {
                    "created": f"{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC",
                    "filter": json.dumps(filters, ensure_ascii=False, sort_keys=True),
                    "name": dataset.export.get("name", dataset.title),
                },
                dashboard_layout(dataset),
            )
            archive.writestr("dashboard.html", html)
            if missing:
                archive.writestr("MISSING.txt", _missing_text(missing))
        os.replace(temp_path, final_path)
    finally:
        reader.close()
        if os.path.exists(temp_path):
            os.remove(temp_path)

    size = os.path.getsize(final_path)
    prefix = dataset.export.get("file_prefix", f"{dataset.id}_export")
    file_name = f"{prefix}_{datetime.date.today():%Y%m%d}_{export_id[:8]}.zip"
    cur.execute(
        "INSERT INTO _fd.imagehub_exports "
        "(id, owner_id, filter, n_files, file_name, size_bytes, missing) "
        "VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s::jsonb)",
        (export_id, owner_id, json.dumps(filters), len(paths), file_name, size,
         json.dumps(missing)),
    )
    record("imagehub_exports", actor=owner_id, action="create", after={
        "id": export_id, "dataset": dataset.id, "filter": filters, "n_files": len(paths), "n_missing": len(missing),
    })
    return {
        "id": export_id, "n_files": len(paths), "n_missing": len(missing),
        "missing": missing, "size_bytes": size, "file_name": file_name, "path": final_path,
        "dashboard_note": dashboard_note,
    }
