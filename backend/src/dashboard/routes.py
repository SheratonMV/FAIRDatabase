"""Flask blueprint routes for dashboard features: upload, search, display,
   preview, and update of PostgreSQL-stored CSV data."""

from flask import (
    render_template,
    session,
    request,
    redirect,
    Blueprint,
    make_response,
    url_for,
    flash,
    g,
    current_app,
    jsonify,
    )

from .helpers import (
    pg_ensure_schema_and_metadata,
    pg_create_data_table,
    pg_insert_metadata,
    pg_insert_data_rows,
    file_chunk_columns,
    file_save_and_read,
    filter_owned_tables,
    filter_readable_tables,
    assert_can_read_table,
)

from config import Error
from src.exceptions import GenericExceptionHandler
from src.auth.decorators import login_required
from io import BytesIO
from psycopg2 import sql


import os
import zipfile
import pandas as pd

import logging
_log = logging.getLogger(__name__)

routes = Blueprint("dashboard_routes", __name__)


def _manageable_datasets(conn):
    """Return ``{table_name: dataset_id}`` for datasets the caller can manage
    grants on. Admins see everything; curators see only their own datasets;
    everyone else gets an empty mapping.
    """
    role = getattr(g, "role", None)
    user_id = getattr(g, "user", None)
    if role not in ("admin", "curator") or not user_id:
        return {}
    try:
        with conn.cursor() as cur:
            if role == "admin":
                cur.execute(
                    "SELECT table_name, id FROM _fd.metadata_tables"
                )
            else:
                cur.execute(
                    "SELECT table_name, id FROM _fd.metadata_tables "
                    "WHERE owner_id = %s",
                    (user_id,),
                )
            return {row[0]: row[1] for row in cur.fetchall()}
    except Exception:
        conn.rollback()
        return {}


@routes.route("/")
@login_required()
def dashboard():
    user_email = session["email"]
    return (
        render_template(
            "/dashboard/dashboard.html",
            user_email=user_email,
            current_path=request.path,
        ),
        200,
    )


@routes.route("/upload", methods=["GET", "POST"])
@login_required("admin", "curator")
def upload():
    """
    Upload CSV file, process and store chunks in PostgreSQL tables.
    ---
    tags:
      - upload
    consumes:
      - multipart/form-data
    parameters:
      - name: file
        in: formData
        type: file
        required: true
        description: CSV file to upload.
      - name: description
        in: formData
        type: string
        required: false
        description: Optional description of file.
      - name: origin
        in: formData
        type: string
        required: false
        description: Origin/source of data.
    responses:
      200:
        description: File uploaded and processed successfully.
      400:
        description: Error during file processing.
    """
    user_email = session.get("email", "")
    conn = g.db

    if request.method == "POST":
        file = request.files.get("file", "")

        if not file or file.filename.strip() == "":
            flash("No file selected. Please upload a valid CSV file.", "danger")
            return redirect(url_for("dashboard_routes.upload"))

        try:
            description = request.form.get("description", "")
            origin = request.form.get("origin", "")
            lines, filename = file_save_and_read(file)
            if len(lines) < 2:
                return jsonify({"status": "error", "message": "CSV file is empty or has no data rows."}), 400
            header, rows = lines[0], lines[1:]
            if len(header) < 2:
                return jsonify({"status": "error", "message": "CSV must have at least two columns (a patient ID column and one data column)."}), 400
            patient_col, columns = header[0], header[1:]
            chunks = file_chunk_columns(columns, 1200)
            main_table = filename.rsplit(".", 1)[0]
            schema = "fd"
            # created a new schema called _fd to store the uploaded datasets. Realtime can not be used anymore due to restrictions with supabase


            with conn.cursor() as cur:
                pg_ensure_schema_and_metadata(cur, schema)
                for i, chunk in enumerate(chunks):
                    table = f"{main_table}_p{i+1}"
                    pg_create_data_table(
                        cur, schema, table, chunk, patient_col)
                    pg_insert_metadata(
                        cur, schema, table, main_table, description, origin,
                        owner_id=g.user,
                    )
                    pg_insert_data_rows(cur, schema, table,
                                        patient_col, rows, chunk, i)

            conn.commit()

            os.remove(os.path.join(
                current_app.config["UPLOAD_FOLDER"], filename))

            # show that it is uploaded succesfully
            return jsonify({"status": "success", "message": f"Dataset '{main_table}' uploaded successfully! {len(chunks)} table(s) created."}), 200

        except Exception:
            conn.rollback()
            _log.exception("dataset upload failed")
            return jsonify({"status": "error", "message": "Upload failed. Check that the file is a valid CSV and try again."}), 400

    return render_template("/dashboard/upload.html", user_email=user_email)


@routes.route("/display", methods=["GET", "POST"])
@login_required("admin", "curator", "accessor")
def display():
    """
    Search and download filtered database tables as zipped CSVs.
    ---
    tags:
      - display
    parameters:
      - name: user
        in: session
        type: string
        required: true
        description: The session identifier of the logged-in user.
      - name: search_term
        in: session
        type: array
        items:
          type: string
        required: true
        description: List of search parameters [column_name, match_value, is_zero_filter].
    responses:
      200:
        description: ZIP file containing matched table CSVs.
        content:
          application/octet-stream:
            schema:
              type: string
              format: binary
      400:
        description: Invalid input or query failure.
      401:
        description: User not logged in.
    """
    user_email = session.get("email")
    search_term = session.get("search_term")
    conn = g.db

    if request.method == "GET" and search_term:
        search_column, _, _ = search_term

        try:

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT table_name
                    FROM information_schema.columns
                    WHERE column_name ILIKE %s
                    AND table_schema = '_fd';
                    """,
                    (f"%{search_column}%",),
                )
                matching_tables = [row[0] for row in cur.fetchall()]
                matching_tables = filter_readable_tables(
                    cur, matching_tables, g.user, g.role
                )
        except Error:
            conn.rollback()
            _log.exception("schema query failed")
            raise GenericExceptionHandler(
                "Schema query failed.", status_code=500
            )

        results = {}
        total_rows = total_columns = 0

        for table in matching_tables:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = '_fd'
                        AND table_name = %s;
                        """,
                        (table,),
                    )
                    columns = [row[0] for row in cur.fetchall()]

                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL("SELECT * FROM {}.{}").format(
                            sql.Identifier("_fd"),
                            sql.Identifier(table),
                        )
                    )

                    rows = cur.fetchall()

                if not rows:
                    continue

                df = pd.DataFrame(rows, columns=columns)
                if not df.empty:
                    df.drop(df.columns[0], axis=1, inplace=True)

                results[table] = df
                total_rows += len(rows)
                total_columns += len(columns)

            except Error:
                conn.rollback()
                _log.exception("schema query failed")
                raise GenericExceptionHandler(
                    "Schema query failed.", status_code=500
                )

        if not results:
            raise GenericExceptionHandler(
                "No matching data found", status_code=404)

        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, "w") as zf:
            for table, df in results.items():
                csv_buffer = BytesIO()
                df.to_csv(csv_buffer, index=False)
                zf.writestr(f"{table}.csv", csv_buffer.getvalue())

        memory_file.seek(0)

        response = make_response(memory_file.getvalue())
        response.headers["Content-Disposition"] = "attachment; filename=tables.zip"
        response.headers["Content-Type"] = "application/octet-stream"
        return response

    return render_template("/dashboard/search.html", user_email=user_email)


@routes.route("/search", methods=["GET", "POST"])
@login_required("admin", "curator", "accessor")
def search():
    """
    Search and display PostgreSQL table names and matching column results.
    ---
    tags:
      - search
    parameters:
      - name: user
        in: session
        type: string
        required: true
        description: The session identifier of the logged-in user.
      - name: search
        in: formData
        type: string
        required: false
        description: Search term for matching column names.
      - name: value0
        in: formData
        type: string
        required: false
        description: Optional filter value for search (e.g. "0" or "1").
      - name: value1
        in: formData
        type: string
        required: false
        description: Optional filter value for search (e.g. "1" or "0").
    responses:
      200:
        description: HTML page showing matched table names or full list.
      302:
        description: Redirect to the display download route if 'Download' is selected.
      401:
        description: User is not logged in.
    """
    user_email = session["email"]
    current_path = request.path
    conn = g.db

    if request.method == "GET":
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT table_name
                FROM information_schema.tables
                WHERE table_schema = '_fd';
            """
            )

            table_names = [row[0] for row in cur.fetchall()]
            table_names = filter_readable_tables(
                cur, table_names, g.user, g.role
            )

        manageable = _manageable_datasets(conn)

        return render_template(
            "/dashboard/search.html",
            table_names=table_names,
            manageable=manageable,
            user_email=user_email,
            current_path=current_path,
        )

    if request.method == "POST":
        if "Download" in request.form:
            return redirect(url_for("dashboard_routes.display"), code=302)

        search_term = request.form.get("search", "").strip()
        seq_na = request.form.get("value0")
        seq_a = request.form.get("value1")

        session["search_term"] = [search_term, seq_a, seq_na]

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT table_name
                    FROM information_schema.columns
                    WHERE column_name ILIKE %s
                    AND table_schema = '_fd';
                """,
                    (f"%{search_term}%",),
                )
                search_results = [row[0] for row in cur.fetchall()]
                search_results = filter_readable_tables(
                    cur, search_results, g.user, g.role
                )

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT table_name
                    FROM information_schema.tables
                    WHERE table_schema = '_fd';
                """
                )
                table_names = [row[0] for row in cur.fetchall()]
                table_names = filter_readable_tables(
                    cur, table_names, g.user, g.role
                )

        except Error:
            conn.rollback()
            _log.exception("search row fetch failed")
            raise GenericExceptionHandler(
                "Failed to fetch rows.", status_code=500
            )

        manageable = _manageable_datasets(conn)

        return render_template(
            "/dashboard/search.html",
            search_results=search_results,
            search_term=search_term,
            table_names=table_names,
            manageable=manageable,
            user_email=user_email,
            current_path=current_path,
        )


@routes.route("/update", methods=["GET", "POST"])
@login_required("admin", "curator")
def update():
    """
    Route to render and handle user update requests.
    ---
    tags:
      - update
    parameters:
      - name: user_email
        in: session
        type: string
        required: true
        description: Email of the logged-in user.
    responses:
      200:
        description: Renders the update page for the user.
      401:
        description: Error response if the user is not logged in.
    """
    user_email = session["email"]
    conn = g.db

    if request.method == "POST":
        row_id = request.form.get("row_id")
        column_name = request.form.get("column_name")
        new_value = request.form.get("new_value")

        if not column_name or not row_id:
            raise GenericExceptionHandler(
                "Row id and column name are required", status_code=400
            )

        with conn.cursor() as cur:
            # Only uploaded datasets (rows in metadata_tables) that have both
            # the exact column named and a rowid column. The old lookup was a
            # substring match over every _fd table, app tables (roles,
            # grants, audit) included, and then wrote to the typed name.
            try:
                cur.execute(
                    """
                    SELECT DISTINCT c.table_name
                    FROM information_schema.columns c
                    JOIN _fd.metadata_tables m ON m.table_name = c.table_name
                    WHERE c.table_schema = '_fd'
                      AND c.column_name = %s
                      AND EXISTS (
                          SELECT 1 FROM information_schema.columns r
                          WHERE r.table_schema = '_fd'
                            AND r.table_name = c.table_name
                            AND r.column_name = 'rowid');
                    """,
                    (column_name,),
                )
            except Error:
                conn.rollback()
                _log.exception("update: column lookup failed")
                raise GenericExceptionHandler(
                    "Failed to look up the column", status_code=500
                )

            tables = [row[0] for row in cur.fetchall()]
            tables = filter_owned_tables(cur, tables, g.user, g.role)

            if not tables:
                raise GenericExceptionHandler(
                    "No matching data found", status_code=404)

            try:
                for table in tables:
                    assert_can_modify_table(cur, table, g.user, g.role)
                    cur.execute(
                        sql.SQL("UPDATE {}.{} SET {} = %s WHERE rowid = %s").format(
                            sql.Identifier("_fd"),
                            sql.Identifier(table),
                            sql.Identifier(column_name),
                        ),
                        (new_value, row_id),
                    )

            except Error:
                conn.rollback()
                _log.exception("update: row update failed")
                raise GenericExceptionHandler(
                    "Failed to update rows", status_code=500
                )

        conn.commit()

    return (
        render_template(
            "/dashboard/update.html", user_email=user_email, current_path=request.path
        ),
        200,
    )


@routes.route("/table_preview", methods=["GET", "POST"])
@login_required("admin", "curator", "accessor")
def table_preview():
    """
    Route to preview table data and display metadata statistics.
    ---
    tags:
      - table-preview
    parameters:
      - name: search_term
        in: session
        type: string
        required: false
        description: Term used to search within table columns.
      - name: table_name
        in: query
        type: string
        required: true
        description: Name of the table to preview.
    responses:
      200:
        description: Renders the preview of the table with metadata stats.
      401:
        description: Error response if the user is not logged in.
    """
    user_email = session.get("email")
    search_term = session.get("search_term", "")
    table_name = request.args.get("table_name")
    conn = g.db

    if not table_name:
        raise GenericExceptionHandler(
            message="Table name is required",
            status_code=400,
        )

    try:
        with conn.cursor() as cur:
            try:
                assert_can_read_table(cur, table_name, g.user, g.role)
            except PermissionError:
                # Surface as 404 to avoid leaking dataset existence to
                # users who don't have access.
                raise GenericExceptionHandler(
                    message=f"Table '{table_name}' not found in _fd schema.",
                    status_code=404,
                )
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = '_fd'
                AND table_name = %s;
                """,
                (table_name,),
            )

            res = cur.fetchone()

    except Error:
        conn.rollback()
        _log.exception("table information query failed")
        raise GenericExceptionHandler(
            message="Error fetching table information.",
            status_code=500,
        )

    if not res:
        raise GenericExceptionHandler(
            message=f"Table '{table_name}' not found in _fd schema.",
            status_code=404,
        )

    with conn.cursor() as cur:
        try:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = '_fd'
                AND table_name = %s;
                """,
                (table_name,),
            )
            columns = [row[0] for row in cur.fetchall()]

            cur.execute(
                sql.SQL("SELECT * FROM {}.{} LIMIT 100;").format(
                    sql.Identifier("_fd"),
                    sql.Identifier(table_name),
                )
            )
            rows = cur.fetchall()

        except Error:
            conn.rollback()
            _log.exception("table preview select failed")
            raise GenericExceptionHandler(
                message="Error selecting data.",
                status_code=500,
            )

    df = pd.DataFrame(rows, columns=columns)
    df_preview = df.iloc[:15, :8]

    metadata_stats = {}
    if "metadata" in df.columns:
        stats = df["metadata"].describe()
        metadata_stats = {
            "count": stats.get("count", 0),
            "unique": stats.get("unique", 0),
            "top": stats.get("top", ""),
            "freq": stats.get("freq", 0),
        }

    tables_html = df_preview.to_html(
        classes="table table-bordered", header="true", index=False
    )

    return (
        render_template(
            "/dashboard/table_preview.html",
            tables=[tables_html],
            table_name=table_name,
            search_term=search_term,
            stats_rows=df.shape[0],
            stats_columns=df.shape[1],
            metadata_stats={table_name: metadata_stats},
            user_email=user_email,
            current_path=request.path,
        ),
        200,
    )


@routes.route("/return_to_dashboard")
@login_required()
def return_to_dashboard():
    """
    Route to return the user to the dashboard and reset session flags related
    to file upload and data review.

    ---
    tags:
      - dashboard
    parameters:
      - name: user_email
        in: session
        type: string
        required: true
        description: The email of the currently logged-in user.
    responses:
      200:
        description: Renders the dashboard page and resets the session flags.
      401:
        description: Error response if the user is not logged in.
    """
    user_email = session["email"]

    session.pop("uploaded_filepath", None)

    flags = [
        "uploaded",
        "columns_dropped",
        "missing_values_reviewed",
        "quasi_identifiers_selected",
        "current_quasi_identifier",
        "all_steps_completed",
    ]
    for flag in flags:
        session[flag] = False

    return (
        render_template(
            "/dashboard/dashboard.html",
            user_email=user_email,
            current_path=request.path,
        ),
        200,
    )
