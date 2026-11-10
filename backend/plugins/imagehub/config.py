"""Dataset configs: one YAML file per dataset. Pure: no Flask, no database.

A dataset config says how to read one collection of sample sheets and image files:
which sheet columns become which fields, how values are cleaned, how an image file
name is parsed and how images are linked to sample rows. The code reads only the
config, so a new dataset needs a new file, not new code.

Files are read from ``datasets/*.yaml`` (shipped examples) and
``datasets/local/*.yaml`` (your own datasets, kept out of git). Every file is
checked when it is loaded: an unknown key, a wrong type or a regex that does not
compile is an error that names the file and the key.

``IMAGEHUB_DATASET`` picks the active dataset. Without it, the active dataset is
the one config that is not marked ``example: true`` (or the only config there is).
"""
import functools
import glob
import os
import re

import yaml

from kernel.env import get as env_get

__all__ = ["ConfigError", "Dataset", "load_file", "load_dir", "datasets", "get", "DATASET_DIRS"]

_HERE = os.path.dirname(os.path.abspath(__file__))
DATASET_DIRS = (os.path.join(_HERE, "datasets"), os.path.join(_HERE, "datasets", "local"))
MAX_FILE_BYTES = 256 * 1024

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
# Steps that clean one value; each works on a list of texts (a single value is a
# list of one). See ``rules.apply_steps``.
_SIMPLE_STEPS = {"strip", "lower", "upper", "drop_empty", "dedupe"}
_STEP_KEYS = {"split", "synonyms", "synonyms_any_case", "split_off_prefix", "replace",
              "lower_capitalised"}


class ConfigError(ValueError):
    """A dataset config that cannot be used; the message names file and key."""


# ── small checkers ────────────────────────────────────────────────────────────

class _Checker:
    def __init__(self, source):
        self.source = source

    def fail(self, path, message):
        raise ConfigError(f"{self.source}: {path}: {message}")

    def mapping(self, value, path, allowed, required=()):
        if not isinstance(value, dict):
            self.fail(path, "must be a mapping")
        unknown = sorted(set(value) - set(allowed))
        if unknown:
            self.fail(path, f"unknown key(s) {', '.join(map(str, unknown))}; allowed: {', '.join(sorted(allowed))}")
        for key in required:
            if key not in value:
                self.fail(path, f"missing key {key}")
        return value

    def text(self, value, path, *, empty=False):
        if not isinstance(value, str) or (not empty and not value.strip()):
            self.fail(path, "must be a non-empty text")
        return value

    def boolean(self, value, path):
        if not isinstance(value, bool):
            self.fail(path, "must be true or false")
        return value

    def integer(self, value, path, minimum=0):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            self.fail(path, f"must be a whole number >= {minimum}")
        return value

    def text_list(self, value, path):
        if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
            self.fail(path, "must be a list of texts")
        return value

    def text_map(self, value, path):
        if not isinstance(value, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in value.items()
        ):
            self.fail(path, "must map texts to texts")
        return value

    def field(self, value, path):
        if not isinstance(value, str) or not _FIELD_RE.match(value):
            self.fail(path, "must be a field name: lower-case letters, digits and _")
        return value

    def fields(self, value, path):
        if not isinstance(value, list):
            self.fail(path, "must be a list of field names")
        return [self.field(v, f"{path}[{i}]") for i, v in enumerate(value)]

    def regex(self, value, path, *, groups=(), flags=0):
        self.text(value, path)
        try:
            compiled = re.compile(value, flags)
        except re.error as exc:
            self.fail(path, f"regex does not compile: {exc}")
        missing = [g for g in groups if g not in compiled.groupindex]
        if missing:
            self.fail(path, f"regex needs the named group(s) {', '.join(missing)}")
        return compiled

    def relative_name(self, value, path):
        """A file or folder name relative to the data root: no absolute paths, no '..'."""
        self.text(value, path)
        parts = value.replace("\\", "/").split("/")
        if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value) or ".." in parts:
            self.fail(path, "must be relative to the data root, without '..'")
        return value

    def steps(self, value, path):
        if not isinstance(value, list):
            self.fail(path, "must be a list of steps")
        for i, step in enumerate(value):
            where = f"{path}[{i}]"
            if isinstance(step, str):
                if step not in _SIMPLE_STEPS:
                    self.fail(where, f"unknown step {step!r}; known: {', '.join(sorted(_SIMPLE_STEPS | _STEP_KEYS))}")
                continue
            if not isinstance(step, dict) or len(step) != 1 or next(iter(step)) not in _STEP_KEYS:
                self.fail(where, f"must be one of {', '.join(sorted(_SIMPLE_STEPS))} or a mapping with one of {', '.join(sorted(_STEP_KEYS))}")
            name, arg = next(iter(step.items()))
            if name == "split":
                self.text(arg, f"{where}.split", empty=False)
            elif name in ("synonyms", "synonyms_any_case"):
                self.text_map(arg, f"{where}.{name}")
            elif name == "replace":
                self.mapping(arg, f"{where}.replace", {"pattern", "with"}, required=("pattern", "with"))
                self.regex(arg["pattern"], f"{where}.replace.pattern")
                self.text(arg["with"], f"{where}.replace.with", empty=True)
            elif name == "lower_capitalised":
                self.mapping(arg, f"{where}.lower_capitalised", {"keep"})
                self.text_list(arg.get("keep") or [], f"{where}.lower_capitalised.keep")
            else:
                self.mapping(arg, f"{where}.split_off_prefix", {"canonical", "variants", "separator"},
                             required=("canonical", "variants", "separator"))
                self.text(arg["canonical"], f"{where}.split_off_prefix.canonical")
                self.text_list(arg["variants"], f"{where}.split_off_prefix.variants")
                self.text(arg["separator"], f"{where}.split_off_prefix.separator")
        return value


def _keys(value):
    """Keys of a mapping whose keys are free names (fields); anything else has none."""
    return set(value) if isinstance(value, dict) else set()


# ── sections ──────────────────────────────────────────────────────────────────

def _check_metadata(c, raw):
    m = c.mapping(raw, "metadata", {
        "legend_sheet", "required", "position", "flag_skipped_with_data", "report_missing",
        "workbook_group_separator", "fields", "derived", "source", "long_report",
    }, required=("fields", "required"))
    if "source" in m:
        c.relative_name(m["source"], "metadata.source")
    fields = c.mapping(m["fields"], "metadata.fields", _keys(m["fields"]))
    if not fields:
        c.fail("metadata.fields", "needs at least one field")
    names = set()
    for name, spec in fields.items():
        path = f"metadata.fields.{name}"
        c.field(name, path)
        c.mapping(spec, path, {"header", "header_regex", "label", "unit_field", "strip"})
        if ("header" in spec) == ("header_regex" in spec):
            c.fail(path, "needs exactly one of header, header_regex")
        if "header" in spec:
            c.text(spec["header"], f"{path}.header")
            for key in ("label", "unit_field"):
                if key in spec:
                    c.fail(f"{path}.{key}", "only goes with header_regex")
        else:
            c.regex(spec["header_regex"], f"{path}.header_regex", groups=("unit",), flags=re.IGNORECASE)
            c.text(spec.get("label", name), f"{path}.label")
            names.add(c.field(spec.get("unit_field", f"{name}_unit"), f"{path}.unit_field"))
        if "strip" in spec:
            c.boolean(spec["strip"], f"{path}.strip")
        names.add(name)
    derived = m.get("derived") or {}
    c.mapping(derived, "metadata.derived", _keys(derived))
    for name, spec in derived.items():
        path = f"metadata.derived.{name}"
        c.field(name, path)
        if name in names:
            c.fail(path, "already a field")
        c.mapping(spec, path, {"from", "steps"}, required=("from", "steps"))
        if c.field(spec["from"], f"{path}.from") not in names:
            c.fail(f"{path}.from", f"no field {spec['from']!r} in metadata.fields")
        c.steps(spec["steps"], f"{path}.steps")
    known = names | set(derived)

    def known_fields(key):
        for i, f in enumerate(c.fields(m.get(key) or [], f"metadata.{key}")):
            if f not in known:
                c.fail(f"metadata.{key}[{i}]", f"no field {f!r}")

    known_fields("required")
    if not m["required"]:
        c.fail("metadata.required", "needs at least one field")
    known_fields("report_missing")
    if "position" in m and c.field(m["position"], "metadata.position") not in known:
        c.fail("metadata.position", f"no field {m['position']!r}")
    if "flag_skipped_with_data" in m:
        f = c.mapping(m["flag_skipped_with_data"], "metadata.flag_skipped_with_data",
                      {"any_of", "min_filled"})
        for i, name in enumerate(c.fields(f.get("any_of") or [], "metadata.flag_skipped_with_data.any_of")):
            if name not in names:
                c.fail(f"metadata.flag_skipped_with_data.any_of[{i}]", f"no field {name!r}")
        if "min_filled" in f:
            c.integer(f["min_filled"], "metadata.flag_skipped_with_data.min_filled", 1)
    if "long_report" in m:
        lr = c.mapping(m["long_report"], "metadata.long_report", {"key", "values"})
        for key in ("key", "values"):
            for i, f in enumerate(c.fields(lr.get(key) or [], f"metadata.long_report.{key}")):
                if f not in known:
                    c.fail(f"metadata.long_report.{key}[{i}]", f"no field {f!r}")
    if "legend_sheet" in m:
        c.text(m["legend_sheet"], "metadata.legend_sheet")
    if "workbook_group_separator" in m:
        c.text(m["workbook_group_separator"], "metadata.workbook_group_separator")
    return known


def _check_images(c, raw, sample_fields):
    im = c.mapping(raw, "images", {
        "extensions", "archives", "skip", "annotation_archive", "filename", "match",
    }, required=("extensions", "archives", "filename"))
    for i, ext in enumerate(c.text_list(im["extensions"], "images.extensions")):
        if not re.match(r"^\.[a-z0-9]+$", ext):
            c.fail(f"images.extensions[{i}]", "must look like .jpg (lower case)")
    if not isinstance(im["archives"], list) or not im["archives"]:
        c.fail("images.archives", "must be a non-empty list")
    zips = set()
    for i, a in enumerate(im["archives"]):
        path = f"images.archives[{i}]"
        c.mapping(a, path, {"zip", "group", "folder_level"}, required=("zip", "folder_level"))
        zips.add(c.relative_name(a["zip"], f"{path}.zip"))
        if "group" in a:
            c.text(a["group"], f"{path}.group")
        c.integer(a["folder_level"], f"{path}.folder_level", 1)
    for i, s in enumerate(im.get("skip") or []):
        c.mapping(s, f"images.skip[{i}]", {"zip", "folder"}, required=("zip", "folder"))
        c.text(s["zip"], f"images.skip[{i}].zip")
        c.text(s["folder"], f"images.skip[{i}].folder")
    if "annotation_archive" in im:
        a = c.mapping(im["annotation_archive"], "images.annotation_archive",
                      {"zip", "nested_prefix", "nested_groups"}, required=("zip",))
        if c.relative_name(a["zip"], "images.annotation_archive.zip") in zips:
            c.fail("images.annotation_archive.zip", "is also listed in images.archives")
        if "nested_prefix" in a:
            c.text(a["nested_prefix"], "images.annotation_archive.nested_prefix")
        c.text_map(a.get("nested_groups") or {}, "images.annotation_archive.nested_groups")

    f = c.mapping(im["filename"], "images.filename", {"pattern", "ignore_case", "fields"},
                  required=("pattern", "fields"))
    flags = re.IGNORECASE if c.boolean(f.get("ignore_case", False), "images.filename.ignore_case") else 0
    pattern = c.regex(f["pattern"], "images.filename.pattern", flags=flags)
    groups = set(pattern.groupindex)
    out = c.mapping(f["fields"], "images.filename.fields", _keys(f["fields"]))
    seen = set()
    for name, spec in out.items():
        path = f"images.filename.fields.{name}"
        c.field(name, path)
        c.mapping(spec, path, {"groups", "upper", "type", "sum", "else_extension", "copy", "synonyms"})
        sources = [k for k in ("groups", "sum", "copy") if k in spec]
        if len(sources) != 1:
            c.fail(path, "needs exactly one of groups, sum, copy")
        if "groups" in spec:
            for j, g in enumerate(c.text_list(spec["groups"], f"{path}.groups")):
                if g not in groups:
                    c.fail(f"{path}.groups[{j}]", f"no group {g!r} in the pattern")
        if "sum" in spec:
            if not isinstance(spec["sum"], dict) or not spec["sum"]:
                c.fail(f"{path}.sum", "must map groups to whole-number factors")
            for g, factor in spec["sum"].items():
                if g not in groups:
                    c.fail(f"{path}.sum.{g}", f"no group {g!r} in the pattern")
                c.integer(factor, f"{path}.sum.{g}")
        if "copy" in spec and spec["copy"] not in seen:
            c.fail(f"{path}.copy", "must name a field listed before this one")
        if "type" in spec and spec["type"] != "int":
            c.fail(f"{path}.type", "only int is supported")
        if "upper" in spec:
            c.boolean(spec["upper"], f"{path}.upper")
        if "else_extension" in spec:
            c.text_map(spec["else_extension"], f"{path}.else_extension")
        if "synonyms" in spec:
            c.text_map(spec["synonyms"], f"{path}.synonyms")
        seen.add(name)

    if "match" in im:
        _check_match(c, im["match"], seen, sample_fields)
    return seen


def _check_match(c, raw, image_fields, sample_fields):
    mt = c.mapping(raw, "images.match", {
        "keys", "group_field", "ignore_in_names", "lab_tokens", "aliases", "infer_single",
    }, required=("keys",))
    if not isinstance(mt["keys"], list) or not mt["keys"]:
        c.fail("images.match.keys", "must be a non-empty list")
    keys = set()
    for i, key in enumerate(mt["keys"]):
        path = f"images.match.keys[{i}]"
        c.mapping(key, path, {"image", "sample", "upper"}, required=("image", "sample"))
        if c.field(key["image"], f"{path}.image") not in image_fields:
            c.fail(f"{path}.image", f"no field {key['image']!r} in images.filename.fields")
        if key["image"] in keys:
            c.fail(f"{path}.image", "is listed twice")
        keys.add(key["image"])
        if c.field(key["sample"], f"{path}.sample") not in sample_fields:
            c.fail(f"{path}.sample", f"no field {key['sample']!r} in metadata")
        if "upper" in key:
            c.boolean(key["upper"], f"{path}.upper")
    grouped = "group_field" in mt
    if grouped and c.field(mt["group_field"], "images.match.group_field") not in sample_fields:
        c.fail("images.match.group_field", f"no field {mt['group_field']!r} in metadata")
    for key in ("ignore_in_names", "lab_tokens", "aliases", "infer_single"):
        if key in mt and not grouped:
            c.fail(f"images.match.{key}", "needs images.match.group_field")
    if "ignore_in_names" in mt:
        c.regex(mt["ignore_in_names"], "images.match.ignore_in_names", flags=re.IGNORECASE)
    if "lab_tokens" in mt:
        c.regex(mt["lab_tokens"], "images.match.lab_tokens", flags=re.IGNORECASE)
    c.text_map(mt.get("aliases") or {}, "images.match.aliases")
    if "infer_single" in mt:
        inf = c.mapping(mt["infer_single"], "images.match.infer_single", {"field", "groups"},
                        required=("field", "groups"))
        if inf["field"] not in keys:
            c.fail("images.match.infer_single.field", "must be an image field in images.match.keys")
        c.text_list(inf["groups"], "images.match.infer_single.groups")


def _check_annotations(c, raw):
    a = c.mapping(raw, "annotations", {
        "format", "annotator_pattern", "unknown_label", "nested_annotators", "nested_image_folders",
    }, required=("format",))
    if a["format"] != "via":
        c.fail("annotations.format", "only via is supported")
    if "annotator_pattern" in a:
        c.regex(a["annotator_pattern"], "annotations.annotator_pattern", groups=("label",))
    if "unknown_label" in a:
        c.text(a["unknown_label"], "annotations.unknown_label")
    c.text_map(a.get("nested_annotators") or {}, "annotations.nested_annotators")
    c.text_map(a.get("nested_image_folders") or {}, "annotations.nested_image_folders")


# ── pages and export ──────────────────────────────────────────────────────────

# Columns every image row has, whatever the dataset: usable in the export.
BUILTIN_COLUMNS = (
    "image_file", "file_status", "original_name", "match_status", "source_zip",
    "source_member", "source_workbook", "source_sheet", "source_row",
)


def _int_fields(images):
    """Image fields that hold whole numbers: ``type: int`` or a ``sum``."""
    return {
        name for name, spec in images["filename"]["fields"].items()
        if spec.get("type") == "int" or "sum" in spec
    }


class _Refs:
    """Checks a field reference: ``group`` (the image's experiment or folder),
    ``image.<field>`` (from the file name) or ``sample.<field>`` (from the sheet)."""

    def __init__(self, image_fields, sample_fields):
        self.image, self.sample = set(image_fields), set(sample_fields)

    def check(self, c, value, path, *, builtin=False, kinds=("group", "image", "sample")):
        if builtin and value in BUILTIN_COLUMNS:
            return value
        if not isinstance(value, str):
            c.fail(path, "must be group, image.<field> or sample.<field>")
        kind, _, name = value.partition(".")
        if value == "group" and "group" in kinds:
            return value
        known = {"image": self.image, "sample": self.sample}.get(kind)
        if kind not in kinds or known is None or not name:
            c.fail(path, f"must be one of: {', '.join(k if k == 'group' else k + '.<field>' for k in kinds)}"
                         + (", or a built-in column" if builtin else ""))
        if name not in known:
            c.fail(path, f"no {kind} field {name!r}")
        return value


def _check_ui(c, raw, refs, int_fields):
    ui = c.mapping(raw, "ui", {
        "group_name", "sample_name", "note", "filters", "sort", "columns",
        "image_details", "sample_details",
    })
    for key in ("group_name", "sample_name", "note"):
        if key in ui:
            c.text(ui[key], f"ui.{key}")
    params = set()
    for i, f in enumerate(ui.get("filters") or []):
        path = f"ui.filters[{i}]"
        c.mapping(f, path, {"param", "params", "field", "type", "label", "labels", "scale", "form"},
                  required=("field", "type"))
        if f["type"] not in ("select", "text", "range"):
            c.fail(f"{path}.type", "must be select, text or range")
        field = refs.check(c, f["field"], f"{path}.field")
        if f["type"] == "range":
            if not field.startswith("image.") or field[6:] not in int_fields:
                c.fail(f"{path}.field", "a range needs an image field of whole numbers")
            names = f.get("params")
            if not isinstance(names, list) or len(names) != 2:
                c.fail(f"{path}.params", "a range needs two params: from and to")
            if "labels" in f and (not isinstance(f["labels"], list) or len(f["labels"]) != 2):
                c.fail(f"{path}.labels", "a range needs two labels")
            if "scale" in f and (not isinstance(f["scale"], (int, float)) or isinstance(f["scale"], bool)
                                 or f["scale"] <= 0):
                c.fail(f"{path}.scale", "must be a number above 0")
        else:
            names = [f.get("param")]
            for key in ("params", "labels", "scale"):
                if key in f:
                    c.fail(f"{path}.{key}", "only goes with type range")
        for name in names:
            if not isinstance(name, str) or not _FIELD_RE.match(name):
                c.fail(path, "needs param names: lower-case letters, digits and _")
            if name in params or name in RESERVED_PARAMS:
                c.fail(path, f"param {name!r} is already used")
            params.add(name)
        if "label" in f:
            c.text(f["label"], f"{path}.label")
        if "form" in f:
            c.boolean(f["form"], f"{path}.form")
    for i, field in enumerate(ui.get("sort") or []):
        refs.check(c, field, f"ui.sort[{i}]")

    def rows(key):
        for i, row in enumerate(ui.get(key) or []):
            path = f"ui.{key}[{i}]"
            c.mapping(row, path, {"label", "field", "fields", "unit", "raw", "format", "optional"},
                      required=("label",))
            c.text(row["label"], f"{path}.label")
            if ("field" in row) == ("fields" in row):
                c.fail(path, "needs exactly one of field, fields")
            for j, field in enumerate(row.get("fields") or [row.get("field")]):
                refs.check(c, field, f"{path}.field" if "field" in row else f"{path}.fields[{j}]")
            for extra in ("unit", "raw"):
                if extra in row:
                    refs.check(c, row[extra], f"{path}.{extra}")
            if "format" in row and row["format"] != "minutes":
                c.fail(f"{path}.format", "only minutes is supported")
            if "optional" in row:
                c.boolean(row["optional"], f"{path}.optional")

    for key in ("columns", "image_details", "sample_details"):
        rows(key)


# Query parameters the pages use themselves, whatever the dataset.
RESERVED_PARAMS = {"dataset", "page", "min_regions", "annotated", "in_bucket"}


def _check_export(c, raw, refs):
    ex = c.mapping(raw, "export", {"name", "file_prefix", "contents", "sections", "sheet_columns", "notes",
                                   "exclude"}, required=("sections",))
    if "exclude" in ex:
        c.text_list(ex["exclude"], "export.exclude")
    for key in ("name", "file_prefix"):
        if key in ex:
            c.text(ex[key], f"export.{key}")
    if "file_prefix" in ex and not _FIELD_RE.match(ex["file_prefix"]):
        c.fail("export.file_prefix", "must be lower-case letters, digits and _")
    if "contents" in ex:
        c.text_map(ex["contents"], "export.contents")
    if "notes" in ex:
        n = c.mapping(ex["notes"], "export.notes", {"min_words", "except", "description"},
                      required=("min_words",))
        c.integer(n["min_words"], "export.notes.min_words", 1)
        c.text_list(n.get("except") or [], "export.notes.except")
        if "description" in n:
            c.text(n["description"], "export.notes.description")
    if "sheet_columns" in ex:
        sc = c.mapping(ex["sheet_columns"], "export.sheet_columns", {"intro", "merge", "groups", "other"},
                       required=("other",))
        if "intro" in sc:
            c.text_list(sc["intro"], "export.sheet_columns.intro")
        c.text_map(sc.get("merge") or {}, "export.sheet_columns.merge")
        c.text(sc["other"], "export.sheet_columns.other")
        for i, g in enumerate(sc.get("groups") or []):
            path = f"export.sheet_columns.groups[{i}]"
            c.mapping(g, path, {"title", "match", "exclude"}, required=("title", "match"))
            c.text(g["title"], f"{path}.title")
            c.regex(g["match"], f"{path}.match", flags=re.IGNORECASE)
            if "exclude" in g:
                c.regex(g["exclude"], f"{path}.exclude")
    if not isinstance(ex["sections"], list) or not ex["sections"]:
        c.fail("export.sections", "must be a non-empty list")
    names, blocks = set(), set()
    for i, section in enumerate(ex["sections"]):
        path = f"export.sections[{i}]"
        block = next((k for k in ("annotations", "sheet_columns", "notes") if isinstance(section, dict) and k in section), None)
        if block:
            c.mapping(section, path, {block})
            if block in blocks:
                c.fail(path, f"{block} is listed twice")
            blocks.add(block)
            if block == "sheet_columns":
                c.boolean(section[block], f"{path}.sheet_columns")
                if "sheet_columns" not in ex:
                    c.fail(path, "needs export.sheet_columns")
            else:
                c.text(section[block], f"{path}.{block}")
                if block == "notes" and "notes" not in ex:
                    c.fail(path, "needs export.notes")
            continue
        c.mapping(section, path, {"title", "columns"}, required=("title", "columns"))
        c.text(section["title"], f"{path}.title")
        if not isinstance(section["columns"], list) or not section["columns"]:
            c.fail(f"{path}.columns", "must be a non-empty list")
        for j, col in enumerate(section["columns"]):
            cp = f"{path}.columns[{j}]"
            c.mapping(col, cp, {"name", "from", "description", "steps", "join", "divide", "round", "only_if"},
                      required=("name", "description"))
            if not isinstance(col["name"], str) or not col["name"].strip():
                c.fail(f"{cp}.name", "must be a non-empty text")
            if col["name"] in names:
                c.fail(f"{cp}.name", f"column {col['name']!r} is listed twice")
            names.add(col["name"])
            c.text(col["description"], f"{cp}.description")
            if "from" not in col and col["name"] not in BUILTIN_COLUMNS:
                c.fail(cp, "needs from, unless the name is a built-in column: " + ", ".join(BUILTIN_COLUMNS))
            if "from" in col:
                refs.check(c, col["from"], f"{cp}.from", builtin=True)
            if "steps" in col:
                c.steps(col["steps"], f"{cp}.steps")
            if "join" in col:
                c.text(col["join"], f"{cp}.join", empty=True)
            if "divide" in col:
                c.integer(col["divide"], f"{cp}.divide", 1)
            if "round" in col:
                c.integer(col["round"], f"{cp}.round", 0)
            if "only_if" in col:
                refs.check(c, col["only_if"], f"{cp}.only_if", builtin=True)


_DASHBOARD_KEYS = {
    "title", "group", "key", "label", "time", "channel", "units", "caption", "expected",
    "not_measured", "not_grouped", "colour_by", "compare_by", "values", "annotator", "tabs",
    "sample_fields",
}
_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


def _check_dashboard(c, raw, refs, export_columns, excluded):
    """Names in ``dashboard`` are metadata.csv columns. Those that pick one column
    must be a column of export.sections; preference lists may name sheet columns."""
    d = c.mapping(raw, "dashboard", _DASHBOARD_KEYS)

    def column(value, path):
        c.text(value, path)
        if value not in export_columns:
            c.fail(path, f"no column {value!r} in export.sections")
        if value.strip().casefold() in excluded:
            c.fail(path, f"column {value!r} is in export.exclude")
        return value

    def columns(value, path):
        c.text_list(value, path)
        return [column(v, f"{path}[{i}]") for i, v in enumerate(value)]

    for key in ("title", "annotator"):
        if key in d:
            c.text(d[key], f"dashboard.{key}")
    if "group" in d:
        column(d["group"], "dashboard.group")
    for key in ("key", "time", "channel", "expected"):
        if key in d:
            columns(d[key], f"dashboard.{key}")
    for key in ("not_measured", "not_grouped", "colour_by", "compare_by", "values"):
        if key in d:
            c.text_list(d[key], f"dashboard.{key}")
    if "label" in d:
        c.text(d["label"], "dashboard.label")
        for name in _PLACEHOLDER_RE.findall(d["label"]):
            column(name, "dashboard.label")
    if "units" in d:
        c.text_map(d["units"], "dashboard.units")
        for value, unit in d["units"].items():
            column(value, "dashboard.units")
            column(unit, f"dashboard.units.{value}")
    if "caption" in d:
        cap = c.mapping(d["caption"], "dashboard.caption", {"title", "text"})
        if "title" in cap:
            column(cap["title"], "dashboard.caption.title")
        if "text" in cap:
            columns(cap["text"], "dashboard.caption.text")
    if "tabs" in d:
        c.mapping(d["tabs"], "dashboard.tabs", {"overview", "images", "time", "flow", "scatter", "annot"})
        c.text_map(d["tabs"], "dashboard.tabs")
    if "sample_fields" in d:
        # Sample rows without images have no image fields: where the key columns come from.
        c.text_map(d["sample_fields"], "dashboard.sample_fields")
        for name, ref in d["sample_fields"].items():
            if name not in d.get("key", []):
                c.fail("dashboard.sample_fields", f"{name!r} is not in dashboard.key")
            refs.check(c, ref, f"dashboard.sample_fields.{name}", kinds=("group", "sample"))


def excluded_names(export):
    """The export's excluded column names, compared without case and outer spaces."""
    return {name.strip().casefold() for name in export.get("exclude") or ()}


def _check_exclude_filters(c, raw):
    """A filter on an excluded column would put its value in the export's filter line."""
    excluded = excluded_names(raw["export"])
    columns = {col["name"]: col.get("from", col["name"]) for s in raw["export"]["sections"]
               if "columns" in s for col in s["columns"]}
    for i, f in enumerate((raw.get("ui") or {}).get("filters") or ()):
        names = {f["field"].rpartition(".")[2], *(f.get("params") or [f.get("param")])}
        names |= {n for n, ref in columns.items() if ref == f["field"]}
        hit = sorted(n for n in names if n and n.strip().casefold() in excluded)
        if hit:
            c.fail("export.exclude", f"{hit[0]!r} is also filtered on by ui.filters[{i}]; "
                                     "its value would show in the export's filter line")


def _export_columns(raw):
    return {col["name"] for s in raw["sections"] if "columns" in s for col in s["columns"]}


# ── the dataset object ────────────────────────────────────────────────────────

class Dataset:
    """A checked config. ``raw`` is the parsed YAML; compiled regexes are attributes."""

    def __init__(self, raw, source="<config>"):
        c = _Checker(source)
        c.mapping(raw, "(top)", {"id", "title", "example", "metadata", "images", "annotations",
                                 "ui", "export", "dashboard"},
                  required=("id", "title", "metadata", "images"))
        if not isinstance(raw["id"], str) or not _ID_RE.match(raw["id"]):
            c.fail("id", "must be 1-40 characters: a lower-case letter, then letters, digits or _")
        c.text(raw["title"], "title")
        c.boolean(raw.get("example", False), "example")
        sample_fields = _check_metadata(c, raw["metadata"])
        image_fields = _check_images(c, raw["images"], sample_fields)
        refs = _Refs(image_fields, sample_fields)
        if "ui" in raw:
            _check_ui(c, raw["ui"], refs, _int_fields(raw["images"]))
        if "export" in raw:
            _check_export(c, raw["export"], refs)
            _check_exclude_filters(c, raw)
        if "dashboard" in raw:
            if "export" not in raw:
                c.fail("dashboard", "needs export")
            _check_dashboard(c, raw["dashboard"], refs, _export_columns(raw["export"]),
                             excluded_names(raw["export"]))
        if "annotations" in raw:
            _check_annotations(c, raw["annotations"])

        self.raw = raw
        self.source = source
        self.id = raw["id"]
        self.title = raw["title"]
        self.example = raw.get("example", False)
        self.metadata = raw["metadata"]
        self.images = raw["images"]
        self.annotations = raw.get("annotations") or {}
        self.ui = raw.get("ui") or {}
        self.export = raw.get("export") or {}
        self.dashboard = raw.get("dashboard") or {}
        # Derived sample fields hold lists; image fields of whole numbers are numbers.
        self.sample_lists = set(self.metadata.get("derived") or {})
        self.int_fields = _int_fields(self.images)
        self.image_fields = set(image_fields)

        fn = self.images["filename"]
        self.filename_re = re.compile(fn["pattern"], re.IGNORECASE if fn.get("ignore_case") else 0)
        self.header_res = {
            name: re.compile(spec["header_regex"], re.IGNORECASE)
            for name, spec in self.metadata["fields"].items() if "header_regex" in spec
        }
        match = self.images.get("match") or {}
        self.names_ignore_re = (
            re.compile(match["ignore_in_names"], re.IGNORECASE) if "ignore_in_names" in match else None
        )
        self.tokens_re = (
            re.compile(rf"(?<![a-z0-9])({match['lab_tokens']})(?![a-z0-9])", re.IGNORECASE)
            if "lab_tokens" in match else None
        )
        pattern = self.annotations.get("annotator_pattern")
        self.annotator_re = re.compile(pattern) if pattern else None

    def __repr__(self):
        return f"Dataset({self.id!r})"


def load_file(path):
    """One config file -> Dataset. Raises ConfigError."""
    name = os.path.basename(path)
    if os.path.getsize(path) > MAX_FILE_BYTES:
        raise ConfigError(f"{name}: larger than {MAX_FILE_BYTES // 1024} KB")
    with open(path, encoding="utf-8") as fh:
        try:
            raw = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ConfigError(f"{name}: not valid YAML: {exc}") from None
    return Dataset(raw, name)


def load_dir(*directories):
    """``{id: Dataset}`` for every ``*.yaml`` in the given folders. Ids must be unique."""
    out = {}
    for directory in directories:
        for path in sorted(glob.glob(os.path.join(directory, "*.yaml"))):
            dataset = load_file(path)
            if dataset.id in out:
                raise ConfigError(
                    f"{os.path.basename(path)}: id {dataset.id!r} is also used by {out[dataset.id].source}"
                )
            out[dataset.id] = dataset
    return out


@functools.lru_cache(maxsize=1)
def datasets():
    """All configs in DATASET_DIRS, read once per process."""
    return load_dir(*DATASET_DIRS)


def get(dataset_id=None, available=None):
    """The dataset with this id, or the active one. Raises ConfigError."""
    available = datasets() if available is None else available
    dataset_id = dataset_id or env_get("IMAGEHUB_DATASET") or None
    if dataset_id:
        if dataset_id not in available:
            raise ConfigError(
                f"no dataset {dataset_id!r}; known: {', '.join(sorted(available)) or 'none'}"
            )
        return available[dataset_id]
    own = [d for d in available.values() if not d.example]
    candidates = own or list(available.values())
    if len(candidates) != 1:
        raise ConfigError(
            "set IMAGEHUB_DATASET to one of: " + (", ".join(sorted(available)) or "none (no configs found)")
        )
    return candidates[0]
