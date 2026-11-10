"""Routes for the imagehub plugin, mounted at /imagehub.

Every import is from ``kernel.*``. Every mutation records an audit row. Every
resource has a working delete route that also removes its blob.
"""
import os

from flask import Blueprint, abort, g, jsonify, render_template, request, send_file, url_for

from kernel.audit import record
from kernel.auth import login_required
from kernel.env import get as env_get
from kernel.rbac import assert_owns
from kernel.storage import signed_url

from . import cli as _cli
from . import config
from .export import MAX_IMAGES_REQUEST, ExportError, build_export, export_path
from .helpers import (
    PAGE_SIZE,
    browser_url,
    display_rows,
    image_filter,
    image_order,
    image_status,
    region_to_svg,
)
from .ingest import (
    DISK_ROOT,
    delete_blobs,
    json_blobs_without_annotations,
    select_images,
    upload_image,
)

routes = Blueprint("imagehub_routes", __name__, cli_group="imagehub")
_cli.register(routes)

READ_ROLES = ("admin", "curator", "accessor")
WRITE_ROLES = ("admin", "curator")

MAX_UPLOAD_PER_REQUEST = 50
SIGNED_URL_TTL = 600  # seconds
# Where the browser reaches the storage gateway.
DEFAULT_PUBLIC_STORAGE = "http://localhost:8000"
# Readable on a dark microscopy image, and told apart by shape-independent colour.
ANNOTATOR_COLOURS = ("#00e5ff", "#ffb300", "#ff4081", "#76ff03")

_IMAGE_COLUMNS = (
    "id", "dataset", "well_id", "match_status", "experiment", "fields", "source_zip",
    "source_member", "storage_path", "preview_path", "mime", "size_bytes", "original_name",
)


def _request_dataset():
    """The dataset of ``?dataset=``, or the active one; 404 for an unknown id."""
    try:
        return config.get(request.args.get("dataset") or None)
    except config.ConfigError as exc:
        abort(404, description=str(exc))


def _image_url(storage_path):
    """Short-lived signed URL the browser can open, or None."""
    if not storage_path:
        return None
    return browser_url(
        signed_url(storage_path, SIGNED_URL_TTL),
        env_get("IMAGEHUB_PUBLIC_STORAGE_URL", DEFAULT_PUBLIC_STORAGE),
        env_get("SUPABASE_KEY"),
    )


def _display_url(image):
    """What a page can show: browsers cannot show TIFF, so TIFF needs its preview."""
    if image["preview_path"]:
        return _image_url(image["preview_path"])
    return _image_url(image["storage_path"]) if image["mime"] != "image/tiff" else None


def _disk_connected(source_zip):
    return os.path.exists(os.path.join(DISK_ROOT, source_zip))


def _owner_scope():
    """The owner whose rows this request may see: None for admin (all rows)."""
    return None if g.role == "admin" else str(g.user)


def _check_owner(cur, table, row_id):
    """Ownership check as a JSON response; None when allowed."""
    try:
        assert_owns(cur, f"_fd.imagehub_{table}", "id", str(row_id))
    except FileNotFoundError:
        return jsonify({"error": "not found"}), 404
    except PermissionError:
        return jsonify({"error": "forbidden"}), 403
    return None


def _load_image(cur, image_id):
    """One image with its annotations, or None. Ids become strings."""
    cur.execute(
        f"SELECT {', '.join(_IMAGE_COLUMNS)} FROM _fd.imagehub_images WHERE id = %s",
        (str(image_id),),
    )
    row = cur.fetchone()
    if row is None:
        return None
    image = dict(zip(_IMAGE_COLUMNS, row))
    image["id"] = str(image["id"])
    image["well_id"] = str(image["well_id"]) if image["well_id"] else None
    cur.execute(
        "SELECT id, annotator_label, source, regions, source_file "
        "FROM _fd.imagehub_annotations WHERE image_id = %s "
        "ORDER BY annotator_label, source_file",
        (str(image_id),),
    )
    columns = [d[0] for d in cur.description]
    image["annotations"] = [dict(zip(columns, r)) for r in cur.fetchall()]
    for annotation in image["annotations"]:
        annotation["id"] = str(annotation["id"])
    return image


def _load_well(cur, well_id):
    # The typed columns stay in the API until they are dropped; ``fields`` has all.
    columns = (
        "id", "dataset", "experiment", "source_workbook", "source_sheet", "source_row", "vid",
        "vids", "well", "volgnummer", "treatment_raw", "treatment_norm", "concentration",
        "concentration_unit", "tissue", "stimulation", "stimulation_norm", "fields", "props",
    )
    cur.execute(
        f"SELECT {', '.join(columns)} FROM _fd.imagehub_wells WHERE id = %s",
        (str(well_id),),
    )
    row = cur.fetchone()
    if row is None:
        return None
    well = dict(zip(columns, row))
    well["id"] = str(well["id"])
    return well


def _filter_options(cur, ds, owner_id):
    """Choices per select filter, from the rows of this dataset the user may see."""
    options = {}
    # Every query below has one table, so the bare column name is unambiguous.
    mine, mine_params = ("AND owner_id = %s", (owner_id,)) if owner_id else ("", ())
    for f in ds.ui.get("filters") or ():
        if f["type"] != "select":
            continue
        ref = f["field"]
        if ref == "group":
            cur.execute("SELECT DISTINCT experiment FROM _fd.imagehub_images "
                        f"WHERE dataset = %s AND experiment IS NOT NULL {mine} ORDER BY 1",
                        (ds.id, *mine_params))
        else:
            kind, name = ref.split(".", 1)
            table = "images" if kind == "image" else "wells"
            if kind == "sample" and name in ds.sample_lists:
                cur.execute(f"SELECT DISTINCT v FROM _fd.imagehub_{table}, "
                            "jsonb_array_elements_text(fields -> %s) v "
                            f"WHERE dataset = %s AND jsonb_typeof(fields -> %s) = 'array' {mine} "
                            "ORDER BY 1", (name, ds.id, name, *mine_params))
            else:
                cur.execute(f"SELECT DISTINCT fields ->> %s FROM _fd.imagehub_{table} "
                            f"WHERE dataset = %s AND fields ? %s {mine} ORDER BY 1",
                            (name, ds.id, name, *mine_params))
        options[f["param"]] = [r[0] for r in cur.fetchall()]
    return options


_SEARCH_COLUMNS = (
    "id", "experiment", "match_status", "source_zip", "storage_path", "preview_path", "mime",
    "original_name", "image", "sample", "regions", "well_owner",
)


def _search_images(cur, args, page, ds):
    """Filtered images of one dataset for one page, and the total count. Only the
    user's own images, unless the user is an admin; the linked sample row's fields
    only when the user owns that row too."""
    owner_id = _owner_scope()
    clauses, params = image_filter(args, ds, owner_id=owner_id)
    where = f"WHERE {' AND '.join(clauses)}"
    joins = (
        "FROM _fd.imagehub_images i "
        "LEFT JOIN _fd.imagehub_wells w ON w.id = i.well_id "
    )
    cur.execute(f"SELECT count(*) {joins}{where}", params)
    total = cur.fetchone()[0]
    order, order_params = image_order(ds)
    cur.execute(
        "SELECT i.id, i.experiment, i.match_status, i.source_zip, i.storage_path, "
        "i.preview_path, i.mime, i.original_name, i.fields, w.fields, "
        "(SELECT string_agg(a.annotator_label || ' ' || jsonb_array_length(a.regions), "
        "', ' ORDER BY a.annotator_label) "
        "FROM _fd.imagehub_annotations a WHERE a.image_id = i.id), w.owner_id "
        f"{joins}{where} ORDER BY {order} LIMIT %s OFFSET %s",
        (*params, *order_params, PAGE_SIZE, (page - 1) * PAGE_SIZE),
    )
    images = [dict(zip(_SEARCH_COLUMNS, row)) for row in cur.fetchall()]
    connected = {}
    columns = ds.ui.get("columns") or ()
    for image in images:
        image["id"] = str(image["id"])
        well_owner = image.pop("well_owner")
        if owner_id and well_owner and str(well_owner) != owner_id:
            image["sample"] = None
        source_zip = image["source_zip"]
        if source_zip not in connected:
            connected[source_zip] = _disk_connected(source_zip)
        image["status"] = image_status(image["storage_path"], connected[source_zip])
        image["thumbnail"] = _display_url(image)
        record = {"group": image["experiment"], "image": image["image"], "sample": image["sample"]}
        image["cells"] = [row["text"] for row in display_rows(columns, record)]
    return images, total


def _page_number():
    return max(1, request.args.get("page", 1, type=int))


# ── Pages ─────────────────────────────────────────────────────────────────────

@routes.get("/ui")
@login_required(*READ_ROLES)
def ui():
    """Query page: filters, and a result table with thumbnails."""
    page = _page_number()
    ds = _request_dataset()
    with g.db.cursor() as cur:
        options = _filter_options(cur, ds, _owner_scope())
        images, total = _search_images(cur, request.args, page, ds)
    query = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template(
        "imagehub/index.html",
        images=images, total=total, page=page, page_size=PAGE_SIZE,
        options=options, args=request.args, query=query, ds=ds,
        filters=[f for f in ds.ui.get("filters") or () if f.get("form", True)],
        columns=[c["label"] for c in ds.ui.get("columns") or ()],
        datasets=sorted(config.datasets().values(), key=lambda d: d.title),
    )


@routes.get("/ui/images/<uuid:image_id>")
@login_required(*READ_ROLES)
def image_page(image_id):
    """One image with its annotations drawn over it, and the well metadata."""
    with g.db.cursor() as cur:
        try:
            assert_owns(cur, "_fd.imagehub_images", "id", str(image_id))
        except FileNotFoundError:
            abort(404)
        except PermissionError:
            abort(403)
        image = _load_image(cur, image_id)
        # Matching links across owners; the linked row's data is shown to its
        # owner and to admins only.
        well, well_hidden = None, False
        if image["well_id"]:
            try:
                assert_owns(cur, "_fd.imagehub_wells", "id", image["well_id"])
                well = _load_well(cur, image["well_id"])
            except PermissionError:
                well_hidden = True
    # The image's own dataset; without its config only the fixed rows are shown.
    ds = config.datasets().get(image["dataset"])
    ui = ds.ui if ds else {}
    record = {"group": image["experiment"], "image": image["fields"],
              "sample": well["fields"] if well else {}}
    overlays = []
    for index, annotation in enumerate(image["annotations"]):
        shapes = [region_to_svg(region) for region in annotation["regions"]]
        drawn = [shape for shape in shapes if shape]
        overlays.append({
            "index": index,
            "label": annotation["annotator_label"],
            "source_file": annotation["source_file"],
            "colour": ANNOTATOR_COLOURS[index % len(ANNOTATOR_COLOURS)],
            "shapes": drawn,
            "not_drawn": len(shapes) - len(drawn),
        })
    return render_template(
        "imagehub/image.html",
        image=image, well=well, well_hidden=well_hidden, overlays=overlays,
        title=ds.title if ds else image["dataset"],
        sample_name=ui.get("sample_name", "sample"),
        image_rows=display_rows(ui.get("image_details"), record),
        sample_rows=display_rows(ui.get("sample_details"), record),
        display_url=_display_url(image),
        status=image_status(image["storage_path"], _disk_connected(image["source_zip"])),
    )


# ── API ───────────────────────────────────────────────────────────────────────

@routes.get("/api/images")
@login_required(*READ_ROLES)
def list_images():
    """Same filters as the query page, as JSON."""
    page = _page_number()
    ds = _request_dataset()
    with g.db.cursor() as cur:
        images, total = _search_images(cur, request.args, page, ds)
    return jsonify({"total": total, "page": page, "page_size": PAGE_SIZE, "images": images})


@routes.get("/api/images/<uuid:image_id>")
@login_required(*READ_ROLES)
def get_image(image_id):
    """One image: catalog fields, signed URLs, annotations."""
    with g.db.cursor() as cur:
        denied = _check_owner(cur, "images", image_id)
        if denied:
            return denied
        image = _load_image(cur, image_id)
    image["url"] = _image_url(image["storage_path"])
    image["display_url"] = _display_url(image)
    image["status"] = image_status(image["storage_path"], _disk_connected(image["source_zip"]))
    return jsonify(image)


@routes.get("/api/wells/<uuid:well_id>")
@login_required(*READ_ROLES)
def get_well(well_id):
    with g.db.cursor() as cur:
        denied = _check_owner(cur, "wells", well_id)
        if denied:
            return denied
        well = _load_well(cur, well_id)
    return jsonify(well)


@routes.post("/api/upload")
@login_required(*WRITE_ROLES)
def upload_selection():
    """Upload listed catalog images from the disk to the bucket."""
    image_ids = (request.get_json(silent=True) or {}).get("image_ids") or []
    if not image_ids or len(image_ids) > MAX_UPLOAD_PER_REQUEST:
        return jsonify({"error": f"give 1 to {MAX_UPLOAD_PER_REQUEST} image_ids"}), 400
    with g.db.cursor() as cur:
        owner_id = _owner_scope()
        if owner_id:
            cur.execute(
                "SELECT id FROM _fd.imagehub_images "
                "WHERE id = ANY(%s::uuid[]) AND owner_id <> %s",
                (image_ids, owner_id),
            )
            others = [str(row[0]) for row in cur.fetchall()]
            if others:
                return jsonify({"error": "forbidden", "image_ids": others}), 403
        images = select_images(cur, image_ids=image_ids, limit=MAX_UPLOAD_PER_REQUEST)
        results = []
        for image in images:
            if not image["storage_path"] and not _disk_connected(image["source_zip"]):
                results.append({"id": image["id"], "status": "disk not connected"})
                continue
            results.append({"id": image["id"], "status": upload_image(cur, image)})
        record("imagehub_images", actor=g.user, action="upload", after={
            "ids": [r["id"] for r in results if r["status"] == "uploaded"],
        })
    g.db.commit()
    return jsonify(results)


@routes.delete("/api/images/<uuid:image_id>")
@login_required(*WRITE_ROLES)
def delete_image(image_id):
    """Remove the catalog row, its annotations and its blobs."""
    with g.db.cursor() as cur:
        denied = _check_owner(cur, "images", image_id)
        if denied:
            return denied
        cur.execute(
            "SELECT source_storage_path FROM _fd.imagehub_annotations WHERE image_id = %s",
            (str(image_id),),
        )
        json_paths = [row[0] for row in cur.fetchall()]
        cur.execute(
            "DELETE FROM _fd.imagehub_images WHERE id = %s "
            "RETURNING storage_path, preview_path, source_zip, source_member",
            (str(image_id),),
        )
        storage_path, preview_path, source_zip, source_member = cur.fetchone()
        orphans = json_blobs_without_annotations(cur, json_paths)
        record("imagehub_images", actor=g.user, action="delete", before={
            "id": str(image_id), "source_zip": source_zip,
            "source_member": source_member, "storage_path": storage_path,
        })
    g.db.commit()
    return jsonify({"deleted": str(image_id), "blobs_removed": delete_blobs(storage_path, preview_path, *orphans)})


@routes.delete("/api/annotations/<uuid:annotation_id>")
@login_required(*WRITE_ROLES)
def delete_annotation(annotation_id):
    with g.db.cursor() as cur:
        denied = _check_owner(cur, "annotations", annotation_id)
        if denied:
            return denied
        cur.execute(
            "DELETE FROM _fd.imagehub_annotations WHERE id = %s "
            "RETURNING image_id, annotator_label, source_file, source_storage_path",
            (str(annotation_id),),
        )
        image_id, label, source_file, json_path = cur.fetchone()
        orphans = json_blobs_without_annotations(cur, [json_path])
        record("imagehub_annotations", actor=g.user, action="delete", before={
            "id": str(annotation_id), "image_id": str(image_id),
            "annotator_label": label, "source_file": source_file,
        })
    g.db.commit()
    delete_blobs(*orphans)
    return jsonify({"deleted": str(annotation_id)})


@routes.delete("/api/wells/<uuid:well_id>")
@login_required(*WRITE_ROLES)
def delete_well(well_id):
    """Remove a well. Its images stay in the catalog, unlinked."""
    with g.db.cursor() as cur:
        denied = _check_owner(cur, "wells", well_id)
        if denied:
            return denied
        cur.execute(
            "UPDATE _fd.imagehub_images SET match_status = 'unmatched', "
            "updated_at = now() WHERE well_id = %s",
            (str(well_id),),
        )
        unlinked = cur.rowcount
        cur.execute(
            "DELETE FROM _fd.imagehub_wells WHERE id = %s "
            "RETURNING source_workbook, source_sheet, source_row",
            (str(well_id),),
        )
        workbook, sheet, row = cur.fetchone()
        record("imagehub_wells", actor=g.user, action="delete", before={
            "id": str(well_id), "source_workbook": workbook, "source_sheet": sheet,
            "source_row": row, "images_unlinked": unlinked,
        })
    g.db.commit()
    return jsonify({"deleted": str(well_id), "images_unlinked": unlinked})


@routes.post("/api/export")
@login_required(*WRITE_ROLES)
def create_export():
    """Build one zip from a filter. Missing files are listed, not fatal. Only the
    user's own images, unless the user is an admin."""
    filters = (request.get_json(silent=True) or {}).get("filter") or {}
    with g.db.cursor() as cur:
        try:
            result = build_export(cur, filters, g.user, max_images=MAX_IMAGES_REQUEST,
                                  only_owner=_owner_scope())
        except ExportError as exc:
            g.db.rollback()
            return jsonify({"error": str(exc)}), 400
    g.db.commit()
    return jsonify({
        **result,
        "download_url": url_for("imagehub_routes.download_export", export_id=result["id"]),
    }), 201


@routes.get("/api/exports/<uuid:export_id>/download")
@login_required(*WRITE_ROLES)
def download_export(export_id):
    with g.db.cursor() as cur:
        denied = _check_owner(cur, "exports", export_id)
        if denied:
            return denied
        cur.execute(
            "SELECT file_name FROM _fd.imagehub_exports WHERE id = %s", (str(export_id),)
        )
        file_name = cur.fetchone()[0]
    path = export_path(export_id)
    if not os.path.exists(path):
        return jsonify({"error": "the zip is no longer on the server"}), 404
    return send_file(os.path.abspath(path), as_attachment=True, download_name=file_name)


@routes.delete("/api/exports/<uuid:export_id>")
@login_required(*WRITE_ROLES)
def delete_export(export_id):
    """Remove the export record and its zip."""
    with g.db.cursor() as cur:
        denied = _check_owner(cur, "exports", export_id)
        if denied:
            return denied
        cur.execute(
            "DELETE FROM _fd.imagehub_exports WHERE id = %s RETURNING file_name, n_files",
            (str(export_id),),
        )
        file_name, n_files = cur.fetchone()
        record("imagehub_exports", actor=g.user, action="delete", before={
            "id": str(export_id), "file_name": file_name, "n_files": n_files,
        })
    g.db.commit()
    path = export_path(export_id)
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"deleted": str(export_id)})
