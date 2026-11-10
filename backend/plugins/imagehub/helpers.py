"""Pure helpers for the imagehub plugin.

No Flask globals here (no ``g``, no ``request``, no ``session``): this module
must be unit-testable without an app context.
"""
import datetime
import json
import math
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

PAGE_SIZE = 50
UNKNOWN_ANNOTATOR = "unknown"

# Used by the export's readable values only, until those come from the dataset
# config too. The import cleans values with the config's steps (rules.py).
_MIME_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".tif": "image/tiff", ".tiff": "image/tiff",
    ".png": "image/png",
}
# Things that may separate drugs in a combination but are not split on.
_POSSIBLE_SEPARATOR_RE = re.compile(r"[+,/&]|\band\b")


def to_text(value):
    """Excel cell -> text. Whole-number floats lose their ``.0``; empty -> None."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    text = str(value)
    return text if text.strip() else None


def to_json_value(value):
    """Excel cell -> JSON-serialisable value, keeping numbers as numbers."""
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def treatment_flags(tokens):
    """Normalised tokens worth a human look: {token: reason}.

    Flags what the rules deliberately leave alone: possible unsplit combinations
    and tokens that differ only in punctuation or spacing (abt-199 / abt199).
    """
    flags = {}
    collapsed = {}
    for token in tokens:
        collapsed.setdefault(re.sub(r"[^a-z0-9]", "", token), []).append(token)
        if _POSSIBLE_SEPARATOR_RE.search(token):
            flags[token] = "possible combination, not split"
    for group in collapsed.values():
        if len(group) > 1:
            for token in group:
                others = ", ".join(t for t in group if t != token)
                flags[token] = f"differs only in punctuation from: {others}"
    return flags


def dedupe_headers(headers):
    """Make header cells unique, keeping the original text.

    A repeated name gets ``_2``, ``_3``. A blank header cell becomes
    ``(no header, column N)``, with N counted from 1.
    """
    seen = {}
    out = []
    for index, header in enumerate(headers, start=1):
        name = "" if header is None else str(header)
        if not name.strip():
            out.append(f"(no header, column {index})")
            continue
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return out


def experiment_key(name, ignore=None):
    """Comparison key for experiment names: drops case, punctuation and whatever
    the compiled regex ``ignore`` matches (a dataset's ``ignore_in_names``)."""
    text = ignore.sub("", name or "") if ignore is not None else (name or "")
    return re.sub(r"[^a-z0-9]", "", text.lower())


def experiment_tokens(name, pattern):
    """Lab identifiers in an experiment name, e.g. ``{"EXP36"}``, found by the
    compiled regex ``pattern`` (a dataset's ``lab_tokens``, see config.py)."""
    return {m.group(1).upper() for m in pattern.finditer(name or "")}


def mime_type(filename):
    """Image MIME type from the extension, or None."""
    return _MIME_TYPES.get(filename[filename.rfind("."):].lower())


def safe_name(text):
    """Text as one bucket key or zip folder part: storage refuses some characters
    (``[``, ``]``) in keys."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text or "unknown")


def storage_key(dataset, group, object_id, filename):
    """Bucket key ``<dataset>/<group>/<id>_<file name>``. The dataset comes first,
    so every dataset has its own part of the bucket; the id keeps equal file
    names from different folders apart."""
    return f"{safe_name(dataset)}/{safe_name(group)}/{object_id}_{safe_name(filename)}"


def browser_url(signed, public_base, api_key):
    """Make a signed URL usable in a browser.

    The storage client builds it on the Docker-internal host, and the gateway asks
    for an API key on every storage path, even with a valid token. ``api_key``
    must be the anon key, which is public by design: the token still decides which
    object can be read and for how long.
    """
    if not signed:
        return None
    parts = urlsplit(signed)
    base = urlsplit(public_base)
    query = parse_qsl(parts.query) + [("apikey", api_key)]
    return urlunsplit((base.scheme, base.netloc, parts.path, urlencode(query), ""))


def parse_via(data):
    """VIA export -> ``[{"filename", "size", "regions"}]``.

    Accepts a region-data export and a project file (``_via_img_metadata``), and
    both region layouts (VIA 1 uses a dict, VIA 2 a list). Regions are kept as they
    are: shapes include polygons and ellipses.
    """
    entries = data.get("_via_img_metadata", data)
    out = []
    for entry in entries.values():
        if not isinstance(entry, dict) or "filename" not in entry:
            continue
        regions = entry.get("regions") or []
        if isinstance(regions, dict):
            regions = list(regions.values())
        out.append({
            "filename": entry["filename"],
            "size": entry.get("size"),
            "regions": regions,
        })
    return out


def annotator_label(member, pattern, unknown=UNKNOWN_ANNOTATOR):
    """Label from a VIA file name: the ``label`` group of the compiled regex
    ``pattern``. A name it does not match, or no pattern, gives ``unknown``."""
    match = pattern.search(member) if pattern is not None else None
    return match.group("label") if match else unknown


def _number(value):
    return float(value)


def region_to_svg(region):
    """One VIA region -> ``(svg tag, attributes)``, or None for an unknown shape.

    VIA coordinates are image pixels, so the SVG viewBox must be the image size.
    """
    shape = region.get("shape_attributes") or {}
    name = shape.get("name")
    try:
        if name in ("polygon", "polyline"):
            xs, ys = shape["all_points_x"], shape["all_points_y"]
            points = " ".join(f"{_number(x)},{_number(y)}" for x, y in zip(xs, ys))
            return name, {"points": points}
        if name == "ellipse":
            cx, cy = _number(shape["cx"]), _number(shape["cy"])
            attrs = {"cx": cx, "cy": cy, "rx": _number(shape["rx"]), "ry": _number(shape["ry"])}
            # VIA stores the rotation in radians, SVG wants degrees.
            theta = _number(shape.get("theta") or 0)
            if theta:
                attrs["transform"] = f"rotate({math.degrees(theta)} {cx} {cy})"
            return "ellipse", attrs
        if name == "circle":
            return "circle", {"cx": _number(shape["cx"]), "cy": _number(shape["cy"]), "r": _number(shape["r"])}
        if name == "rect":
            return "rect", {
                "x": _number(shape["x"]), "y": _number(shape["y"]),
                "width": _number(shape["width"]), "height": _number(shape["height"]),
            }
        if name == "point":
            return "circle", {"cx": _number(shape["cx"]), "cy": _number(shape["cy"]), "r": 4.0}
    except (KeyError, TypeError, ValueError):
        return None
    return None


def image_status(storage_path, disk_connected):
    """Where an image can be read from, as shown in the UI."""
    if storage_path:
        return "in bucket"
    return "on disk only" if disk_connected else "disk not connected"


def _ref_sql(ref):
    """SQL for a config field reference, and its bound key (or None)."""
    if ref == "group":
        return "i.experiment", None
    kind, name = ref.split(".", 1)
    return f"{'i' if kind == 'image' else 'w'}.fields -> %s", name


def image_filter(args, dataset, owner_id=None):
    """Filter values -> ``(WHERE clauses, params)``, by the dataset's ``ui.filters``.
    Values are always bound, field names too.

    Expects ``i`` = images and ``w`` = wells (left joined). Only the dataset's own
    images match, and with ``owner_id`` only that user's images; sample fields then
    match only on sample rows that user owns, so a filter cannot reveal the values of
    someone else's row. Blank values and range values that are not numbers are ignored;
    a whole-number field asked for text matches nothing.
    """
    clauses, params = ["i.dataset = %s"], [dataset.id]
    if owner_id:
        clauses.append("i.owner_id = %s")
        params.append(owner_id)

    def add(clause, *values):
        clauses.append(clause)
        params.extend(values)

    def number(name, scale):
        try:
            return int(float(args.get(name, "")) * scale)
        except (ValueError, OverflowError):
            return None

    for f in dataset.ui.get("filters") or ():
        ref = f["field"]
        if f["type"] == "range":
            name = ref.split(".", 1)[1]
            low, high = (number(p, f.get("scale", 1)) for p in f["params"])
            if low is not None:
                add("(i.fields ->> %s)::numeric >= %s", name, low)
            if high is not None:
                add("(i.fields ->> %s)::numeric <= %s", name, high)
            continue
        value = args.get(f["param"])
        if f["type"] == "text" and isinstance(value, str):
            value = value.strip()
        if not value:
            continue
        if ref == "group":
            add("i.experiment = %s", value)
            continue
        kind, name = ref.split(".", 1)
        if kind == "image" and name in dataset.int_fields:
            try:
                value = int(value)
            except (TypeError, ValueError):
                add("false")
                continue
        if kind == "sample" and name in dataset.sample_lists:
            value = [value]
        if kind == "sample" and owner_id:
            add("(w.owner_id = %s AND w.fields @> %s::jsonb)", owner_id, json.dumps({name: value}))
        else:
            add(f"{'i' if kind == 'image' else 'w'}.fields @> %s::jsonb", json.dumps({name: value}))
    try:
        min_regions = int(args.get("min_regions", ""))
    except (TypeError, ValueError):
        min_regions = None
    if min_regions is not None:
        # One annotator must reach it: two annotators' regions overlap, so adding
        # them up would count the same cluster twice.
        add("EXISTS (SELECT 1 FROM _fd.imagehub_annotations a WHERE a.image_id = i.id "
            "AND jsonb_array_length(a.regions) >= %s)", min_regions)
    if args.get("annotated"):
        add("EXISTS (SELECT 1 FROM _fd.imagehub_annotations a WHERE a.image_id = i.id)")
    if args.get("in_bucket"):
        add("i.storage_path IS NOT NULL")
    return clauses, params


def ref_value(ref, record):
    """The value of a field reference in ``{"group", "image", "sample"}``."""
    if ref == "group":
        return record.get("group")
    kind, name = ref.split(".", 1)
    return (record.get(kind) or {}).get(name)


def _text(value, fmt=None):
    if value is None:
        return ""
    if fmt == "minutes":
        return format_minutes(value) if isinstance(value, int) else str(value)
    if isinstance(value, list):
        return " + ".join(str(v) for v in value)
    return str(value)


def display_rows(specs, record):
    """Rows for a page, by ``ui.columns`` / ``ui.*_details``:
    ``[{"label", "text", "raw"}]``. ``optional`` rows without a value are left out."""
    out = []
    for spec in specs or ():
        refs = spec.get("fields") or [spec["field"]]
        values = [ref_value(ref, record) for ref in refs]
        if spec.get("optional") and not any(v not in (None, "", []) for v in values):
            continue
        text = " / ".join(_text(v, spec.get("format")) for v in values)
        if "unit" in spec and values[0] not in (None, ""):
            unit = ref_value(spec["unit"], record)
            text = f"{text} {unit}" if unit else text
        raw = _text(ref_value(spec["raw"], record)) if "raw" in spec else ""
        out.append({"label": spec["label"], "text": text, "raw": raw})
    return out


def image_order(dataset):
    """``(ORDER BY list, params)`` by the dataset's ``ui.sort``, then the source member."""
    parts, params = [], []
    for ref in dataset.ui.get("sort") or ():
        sql, key = _ref_sql(ref)
        parts.append(sql)
        params.extend([key] if key else [])
    return ", ".join([*parts, "i.source_member"]), params


def format_minutes(minutes):
    """``5048`` -> ``"3d 12h 8m"``; empty if the time is unknown."""
    if minutes is None:
        return ""
    return f"{minutes // 1440}d {minutes % 1440 // 60}h {minutes % 60}m"


_ISO_MIDNIGHT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T00:00:00$")
NO_DESCRIPTION = "no description in the lab sheet"
# In a legend sheet this is a ditto mark, not a description.
_DITTO = {'"', "'", "''"}


def export_value(value):
    """A sheet value for the csv: dates as YYYY-MM-DD, the rest unchanged."""
    if isinstance(value, str):
        match = _ISO_MIDNIGHT_RE.match(value)
        if match:
            return match.group(1)
    return value


def legend_key(header):
    """Lookup key: ignores spacing, case and a repeated-header suffix."""
    return re.sub(r"\s+", "", re.sub(r"_\d+$", "", header)).casefold()


def legend_descriptions(rows):
    """Legend sheet rows -> ``{legend_key: description}``, without ditto marks."""
    out = {}
    for row in rows:
        if len(row) < 2 or not row[0] or row[1] is None:
            continue
        text = str(row[1]).strip()
        if text and text not in _DITTO:
            out[legend_key(str(row[0]))] = text
    return out
