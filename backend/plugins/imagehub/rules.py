"""Applying a dataset config to values. Pure: no Flask, no database.

The steps are checked when the config is loaded (config.py); here they are run.
"""
import collections
import re

__all__ = ["apply_steps", "value_mapping", "parse_filename"]


def apply_steps(value, steps):
    """Clean one value with a config's ``steps`` and return a list of texts.

    A text is a list of one; None is an empty list. Steps run in order:
    ``split`` cuts every text on a separator, ``strip``/``lower``/``upper`` change
    each text, ``synonyms`` replaces exact matches and ``synonyms_any_case`` matches
    regardless of capitals, ``split_off_prefix`` cuts a known group off the start
    of a text and writes it one way, ``replace`` substitutes a regex,
    ``lower_capitalised`` lower-cases a single capitalised word (``Ibrutinib``)
    unless it is kept, ``drop_empty`` removes empty texts and ``dedupe`` keeps the
    first of equal texts.
    """
    items = [] if value is None else [value] if isinstance(value, str) else list(value)
    for step in steps:
        if step == "strip":
            items = [t.strip() for t in items]
        elif step == "lower":
            items = [t.lower() for t in items]
        elif step == "upper":
            items = [t.upper() for t in items]
        elif step == "drop_empty":
            items = [t for t in items if t]
        elif step == "dedupe":
            items = list(dict.fromkeys(items))
        elif isinstance(step, dict) and "split" in step:
            items = [part for t in items for part in t.split(step["split"])]
        elif isinstance(step, dict) and "synonyms" in step:
            items = [step["synonyms"].get(t, t) for t in items]
        elif isinstance(step, dict) and "synonyms_any_case" in step:
            table = {k.lower(): v for k, v in step["synonyms_any_case"].items()}
            items = [table.get(t.lower(), t) for t in items]
        elif isinstance(step, dict) and "replace" in step:
            rule = step["replace"]
            items = [re.sub(rule["pattern"], rule["with"], t) for t in items]
        elif isinstance(step, dict) and "lower_capitalised" in step:
            keep = set(step["lower_capitalised"].get("keep") or ())
            items = [t.lower() if _CAPITALISED_RE.match(t) and t not in keep else t for t in items]
        elif isinstance(step, dict) and "split_off_prefix" in step:
            items = _split_off_prefix(items, step["split_off_prefix"])
        else:  # config.py refuses anything else
            raise ValueError(f"unknown step {step!r}")
    return items


_CAPITALISED_RE = re.compile(r"^[A-Z][a-z]+$")


def _split_off_prefix(items, rule):
    """``il2/il15/il21/cpg/acd3/acd28`` -> ``il-2/15/21/cpg``, ``acd3/acd28``."""
    separator, out = rule["separator"], []
    for text in items:
        for variant in rule["variants"]:
            if text == variant or text.startswith(variant + separator):
                out += [rule["canonical"], text[len(variant) + len(separator):]]
                break
        else:
            out.append(text)
    return out


def value_mapping(rows, raw_field, steps):
    """``{raw value: (cleaned list, row count)}``, for review before importing."""
    counts = collections.Counter(row.get(raw_field) for row in rows)
    return {raw: (apply_steps(raw, steps), count) for raw, count in counts.items()}


def parse_filename(dataset, filename):
    """An image file name -> fields, by the config's ``images.filename``; None if
    the name has another form.

    Per field, in config order: take the first filled ``groups`` value, a ``sum``
    of groups times factors, or a ``copy`` of an earlier field; then fill an empty
    value from the file extension (``else_extension``), make it upper case,
    replace ``synonyms`` and convert it to a whole number (``type: int``). A name
    whose ``type: int`` field is not a number counts as another form.
    """
    match = dataset.filename_re.match(filename)
    if not match:
        return None
    out = {}
    for field, spec in dataset.images["filename"]["fields"].items():
        if "groups" in spec:
            value = next((match[g] for g in spec["groups"] if match[g]), None)
        elif "sum" in spec:
            parts = [match[g] for g in spec["sum"]]
            try:
                value = None if any(p is None for p in parts) else sum(
                    int(p) * factor for p, factor in zip(parts, spec["sum"].values())
                )
            except ValueError:
                return None  # a word where the sum needs a number: another form
        else:
            value = out[spec["copy"]]
        if not value and value != 0 and "else_extension" in spec and "." in filename:
            extension = filename.rsplit(".", 1)[1].lower()
            value = spec["else_extension"].get(extension, extension)
        if spec.get("upper") and isinstance(value, str):
            value = value.upper()
        if "synonyms" in spec and isinstance(value, str):
            value = spec["synonyms"].get(value, value)
        if spec.get("type") == "int" and value is not None:
            try:
                value = int(value)
            except ValueError:
                return None  # not a number where the config wants one: another form
        out[field] = value
    return out
