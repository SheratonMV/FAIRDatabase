"""CLI for the imagehub plugin: ``flask imagehub <command>``.

Commands get their connection the way a request does, so audit rows land in
``g.db`` and join the transaction of the change they record.
"""
import collections
import os

import click
from flask import current_app, g

from kernel.audit import record

from . import config
from .export import ExportError, build_export
from .helpers import treatment_flags
from .ingest import (
    DISK_ROOT,
    actor_id,
    annotation_zip,
    derived_mappings,
    image_folders,
    import_via,
    load_match_index,
    match_image,
    propose_aliases,
    read_metadata,
    select_images,
    upload_image,
    upload_via_json,
    walk_images,
    write_catalog_reports,
    write_images,
    write_reports,
    write_wells,
)
from .rules import apply_steps

REPORT_DIR = "uploads/imagehub-reports"
# Filters of the export command that every dataset has; the others come from ui.filters.
BUILTIN_FILTERS = {"min_regions": True, "annotated": False, "in_bucket": False}


def dataset_option(command):
    return click.option(
        "--dataset", "dataset_id", metavar="ID",
        help="Dataset config id. Default: IMAGEHUB_DATASET, or else the one config "
             "that is not an example.",
    )(command)


def _dataset(dataset_id):
    try:
        return config.get(dataset_id)
    except config.ConfigError as exc:
        raise click.ClickException(str(exc))


def _metadata_source(source, ds):
    if source:
        return source
    if "source" not in ds.metadata:
        raise click.UsageError(f"dataset {ds.id} has no metadata.source: give --source")
    return os.path.join(DISK_ROOT, ds.metadata["source"])


def _require_source(source):
    if not os.path.exists(source):
        raise click.ClickException(
            f"{source} not found. Is the disk connected? Mount it in WSL, then run: "
            "docker compose restart flask-app"
        )


def _print_sheets(data, ds):
    required = "/".join(ds.metadata["required"])
    separator = ds.metadata.get("workbook_group_separator")
    click.echo(f"workbook | sheet | cols | rows | no {required} | blank | notes")
    for s in data["sheets"]:
        notes = []
        if s["missing_core"]:
            notes.append("missing " + ",".join(s["missing_core"]))
        for key in sorted(s):
            if key.endswith("_with_data") or key.startswith("wells_without_"):
                notes.append(f"{key}={s[key]}")
        skipped = sum(v for k, v in s.items()
                      if k.startswith("skipped_no_") and not k.endswith("_with_data"))
        workbook = s["workbook"].split(separator)[0] if separator else s["workbook"]
        click.echo(
            f"{workbook} | {s['sheet']} | {s['columns']} | {s.get('wells', 0)} | "
            f"{skipped} | {s.get('skipped_blank', 0)} | {'; '.join(notes)}"
        )
    click.echo(
        f"TOTAL rows={len(data['wells'])} legends={len(data['legends'])} "
        f"skipped={len(data['report'])}"
    )


def _print_mappings(data, ds=None):
    """Per derived field, the raw values that cleaning changes or flags.

    Values that only lose surrounding spaces or are split as written are counted,
    not listed: a VID list would otherwise fill the screen.
    """
    ds = ds or config.get(data["dataset"])
    derived = ds.metadata.get("derived") or {}
    for field, mapping in derived_mappings(data["wells"], ds).items():
        # Only the splitting steps: what the value looks like "as written".
        splitting = [
            step for step in derived[field]["steps"]
            if step in ("strip", "drop_empty") or (isinstance(step, dict) and "split" in step)
        ]
        flags = treatment_flags({t for norm, _ in mapping.values() for t in norm})
        plain = 0
        click.echo(f"\n{field}: raw | cleaned | rows | flag")
        for raw, (norm, count) in sorted(
            mapping.items(), key=lambda kv: str(kv[0]).strip().lower()
        ):
            flag = "; ".join(f"{t}: {flags[t]}" for t in norm if t in flags)
            if norm == apply_steps(raw, splitting) and not flag:
                plain += 1
                continue
            click.echo(f"{raw!r} | {' + '.join(norm)} | {count} | {flag}")
        click.echo(f"({plain} values kept as written)")


def _print_catalog(images):
    totals = collections.Counter(i["match_status"] for i in images)
    click.echo(f"TOTAL images={len(images)} {dict(totals)}")
    click.echo("\nby reason: " + repr(dict(collections.Counter(
        i["match_reason"] for i in images if i["match_reason"]
    ))))
    groups = collections.defaultdict(collections.Counter)
    for i in images:
        groups[(i["source_zip"], i["folder"] or "")][i["match_status"]] += 1
        if i["match_reason"]:
            groups[(i["source_zip"], i["folder"] or "")][i["match_reason"]] += 1
    click.echo("\nfolders that are not fully matched: zip | folder | counts")
    for (zip_name, folder), counts in sorted(groups.items()):
        if counts["unmatched"] or counts["ambiguous"]:
            click.echo(f"{zip_name[:12]} | {folder} | {dict(counts)}")


def register(routes):
    @routes.cli.command("import-metadata")
    @dataset_option
    @click.option("--source", help="xlsx, csv, folder or zip. Default: the config's metadata.source on the disk.")
    @click.option("--as", "email", help="Admin or curator email; needed with --apply.")
    @click.option("--apply", is_flag=True,
                  help="Write to the database. Without it nothing is written.")
    def import_metadata(dataset_id, source, email, apply):
        """Import the sample rows of the sheets (dry run unless --apply)."""
        ds = _dataset(dataset_id)
        source = _metadata_source(source, ds)
        _require_source(source)
        data = read_metadata(source, dataset=ds)
        _print_sheets(data, ds)
        _print_mappings(data, ds)
        if not apply:
            click.echo("\nDRY RUN: nothing written. Use --apply --as <email> to import.")
            return
        if not email:
            raise click.UsageError("--apply needs --as <email>")
        with current_app.test_request_context("/"):
            current_app.preprocess_request()
            with g.db.cursor() as cur:
                owner = actor_id(cur, email)
                status, counts = write_wells(cur, data, owner)
            g.db.commit()
        paths = write_reports(REPORT_DIR, data, status, dataset=ds)
        click.echo(f"\nAPPLIED: {dict(counts)}. Reports: {', '.join(paths)}")

    @routes.cli.command("propose-aliases")
    @dataset_option
    @click.option("--source", help="Default: the config's metadata.source on the disk.")
    def propose_aliases_command(dataset_id, source):
        """Compare image folders on the disk with the groups in the sheets."""
        ds = _dataset(dataset_id)
        source = _metadata_source(source, ds)
        _require_source(source)
        results, unused = propose_aliases(read_metadata(source, dataset=ds)["wells"],
                                          image_folders(DISK_ROOT, dataset=ds), dataset=ds)
        keys = [k["image"] for k in (ds.images.get("match") or {}).get("keys") or ()]
        click.echo(f"kind | zip | folder | experiment | images | ({', '.join(keys)}) in that "
                   f"experiment | {keys[0] if keys else 'first key'} values")
        for r in sorted(results, key=lambda r: (r["kind"] == "exact", r["zip"], r["folder"])):
            click.echo(
                f"{r['kind']} | {r['zip'][:12]} | {r['folder']} | {r['experiment']} | "
                f"{r['images']} | {r['matched']} | {','.join(r['first_values'])}"
            )
        click.echo("\nexperiments with no image folder: " + repr(unused))

    @routes.cli.command("catalog")
    @dataset_option
    @click.option("--as", "email", help="Admin or curator email; needed with --apply.")
    @click.option("--apply", is_flag=True,
                  help="Write to the database. Without it nothing is written.")
    def catalog(dataset_id, email, apply):
        """List the zips and link images to sample rows. Extracts nothing."""
        ds = _dataset(dataset_id)
        if apply and not email:
            raise click.UsageError("--apply needs --as <email>")
        walked = walk_images(DISK_ROOT, dataset=ds)
        if not walked["images"]:
            _require_source(os.path.join(DISK_ROOT, annotation_zip(ds) or ""))
        with current_app.test_request_context("/"):
            current_app.preprocess_request()
            with g.db.cursor() as cur:
                index = load_match_index(cur, dataset=ds)
                images = [match_image(i, index, dataset=ds) for i in walked["images"]]
                _print_catalog(images)
                click.echo(
                    f"\nnot parsed={len(walked['unparsed'])} "
                    f"nested not opened={len(walked['nested'])} "
                    f"zips missing={walked['missing_zips']}"
                )
                status, counts = {}, {}
                if apply:
                    status, counts = write_images(cur, images, actor_id(cur, email))
                paths, without = write_catalog_reports(REPORT_DIR, walked, images, status, cur, dataset=ds)
            g.db.commit()
        click.echo(f"sample rows without images={len(without)} " + repr(dict(
            collections.Counter(w[-1] for w in without)
        )))
        click.echo(("APPLIED: " + repr(dict(counts))) if apply
                   else "DRY RUN: nothing written to the database.")
        click.echo("Reports: " + ", ".join(paths.values()))

    @routes.cli.command("upload")
    @dataset_option
    @click.option("--as", "email", required=True)
    @click.option("--name", help="Exact file name.")
    @click.option("--group", "--experiment", "group", help="The image's group (experiment).")
    @click.option("--field", "fields", multiple=True, metavar="NAME=VALUE",
                  help="An image field from the file name; repeat for more.")
    @click.option("--source-zip")
    @click.option("--annotated", is_flag=True, help="Only images with annotations.")
    @click.option("--limit", default=50, show_default=True)
    def upload(dataset_id, email, name, group, fields, source_zip, annotated, limit):
        """Upload a selection to the bucket. Already uploaded files are skipped."""
        ds = _dataset(dataset_id)
        wanted = _image_fields(fields, ds)
        with current_app.test_request_context("/"):
            current_app.preprocess_request()
            with g.db.cursor() as cur:
                owner = actor_id(cur, email)
                try:
                    images = select_images(
                        cur, name=name, experiment=group, fields=wanted,
                        source_zip=source_zip, annotated=annotated, limit=limit,
                        dataset=ds.id,
                    )
                except ValueError as exc:
                    raise click.UsageError(str(exc))
                results = collections.Counter()
                for image in images:
                    if not image["storage_path"]:
                        _require_source(os.path.join(DISK_ROOT, image["source_zip"]))
                    outcome = upload_image(cur, image)
                    results[outcome] += 1
                    click.echo(f"{outcome} | {image['original_name']} | {image['id']}")
                    g.db.commit()
                record("imagehub_images", actor=owner, action="upload", after=dict(results))
            g.db.commit()
        click.echo(f"DONE: {dict(results)}")

    @routes.cli.command("import-via")
    @dataset_option
    @click.option("--as", "email", required=True)
    @click.option("--zip", "source_zip",
                  help="Zip with the json. Default: the dataset's annotation zip.")
    @click.option("--member", required=True, help="Path of the json inside the zip.")
    @click.option("--only", help="Import one image file name only.")
    @click.option("--upload-json", is_flag=True,
                  help="Also put the original json in the bucket, unchanged.")
    def import_via_command(dataset_id, email, source_zip, member, only, upload_json):
        """Link the regions of a VIA json to catalogued images.

        The annotator comes from the file name by the dataset's annotator_pattern
        (with the example config, set_AA.json is AA); a file with
        no known suffix is 'unknown'.
        """
        ds = _dataset(dataset_id)
        source_zip = source_zip or annotation_zip(ds)
        if not source_zip:
            raise click.UsageError("this dataset has no annotation zip: give --zip")
        _require_source(os.path.join(DISK_ROOT, source_zip))
        with current_app.test_request_context("/"):
            current_app.preprocess_request()
            with g.db.cursor() as cur:
                owner = actor_id(cur, email)
                report = import_via(cur, source_zip, member, owner, only=only, dataset=ds)
                if upload_json:
                    path = upload_via_json(cur, source_zip, member, dataset=ds)
                    record("imagehub_annotations", actor=owner, action="upload_json",
                           after={"storage_path": path})
                    click.echo(f"json in bucket: {path}")
            g.db.commit()
        for filename, status in report:
            click.echo(f"{status} | {filename}")

    @routes.cli.command("export", context_settings={
        "ignore_unknown_options": True, "allow_extra_args": True,
    })
    @dataset_option
    @click.option("--as", "email", required=True)
    @click.option("--min-regions", "min_regions", help="At least this many regions from one annotator.")
    @click.option("--annotated", is_flag=True)
    @click.option("--in-bucket", "in_bucket", is_flag=True)
    @click.option("--max-images", default=2000, show_default=True)
    @click.option("--list-filters", is_flag=True, help="Show the dataset's filters and stop.")
    @click.pass_context
    def export(ctx, dataset_id, email, max_images, list_filters, **builtin):
        """Build one export zip from a filter, same as the Export button.

        The dataset's ui.filters add their own options, by query parameter:
        a parameter from_day is --from-day. See them with --list-filters.
        """
        ds = _dataset(dataset_id)
        params = filter_params(ds)
        if list_filters:
            for param, label in params.items():
                click.echo(f"--{param.replace('_', '-')} | {label}")
            return
        filters = {k: ("1" if v is True else v) for k, v in builtin.items() if v}
        filters.update(_parse_filters(ctx.args, params))
        filters["dataset"] = ds.id
        with current_app.test_request_context("/"):
            current_app.preprocess_request()
            with g.db.cursor() as cur:
                try:
                    result = build_export(
                        cur, filters, actor_id(cur, email), max_images=max_images,
                    )
                except ExportError as exc:
                    raise click.ClickException(str(exc))
            g.db.commit()
        click.echo(
            f"{result['n_files']} files, {result['size_bytes'] / 1048576:.1f} MB, "
            f"{result['n_missing']} missing: {result['path']}"
        )
        if result["dashboard_note"]:
            click.echo(result["dashboard_note"])


def filter_params(ds):
    """``{query parameter: label}`` of the dataset's filters, in config order."""
    params = {}
    for f in ds.ui.get("filters") or ():
        label = f.get("label", f["field"])
        if f["type"] == "range":
            params.update(zip(f["params"], f.get("labels") or (f"{label} from", f"{label} to")))
        else:
            params[f["param"]] = label
    return params


def _parse_filters(args, params):
    """``--name value`` pairs from the extra command line, for the dataset's filters."""
    filters, rest = {}, list(args)
    while rest:
        option = rest.pop(0)
        param = option[2:].replace("-", "_") if option.startswith("--") else None
        if "=" in (param or ""):
            param, value = param.split("=", 1)
            rest.insert(0, value)
        if param not in params:
            raise click.UsageError(
                f"unknown option {option}; this dataset's filters: "
                + ", ".join(f"--{p.replace('_', '-')}" for p in params)
            )
        if not rest:
            raise click.UsageError(f"{option} needs a value")
        filters[param] = rest.pop(0)
    return filters


def _image_fields(pairs, ds):
    """``NAME=VALUE`` texts as image fields; whole-number fields become numbers."""
    names = ds.image_fields
    fields = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or name not in names:
            raise click.UsageError(
                f"--field {pair}: use NAME=VALUE with an image field: {', '.join(sorted(names))}")
        if name in ds.int_fields:
            try:
                value = int(value)
            except ValueError:
                raise click.UsageError(f"--field {pair}: {name} is a whole number")
        fields[name] = value
    return fields
