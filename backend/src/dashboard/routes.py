"""Flask blueprint routes for dashboard features: upload, search, display,
preview, and update of PostgreSQL-stored CSV data."""

import contextlib
import os
import zipfile
from io import BytesIO

import pandas as pd
from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from config import (
    get_cached_table_columns,
    get_cached_tables,
    invalidate_metadata_cache,
    supabase_extension,
)
from src.auth.decorators import login_required
from src.exceptions import GenericExceptionHandler
from src.types import ColumnInfoResult, TableDataResult, TableNameResult

from .helpers import (
    file_chunk_columns,
    file_save_and_read,
    pg_create_data_table,
    pg_ensure_schema_and_metadata,
    pg_insert_data_rows,
    pg_insert_metadata,
)

routes = Blueprint("dashboard_routes", __name__)


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
@login_required()
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

        temp_filepath = None
        try:
            description = request.form.get("description", "")
            origin = request.form.get("origin", "")

            # Use tempfile for automatic cleanup
            lines, temp_filepath = file_save_and_read(file)
            header, rows = lines[0], lines[1:]
            patient_col, columns = header[0], header[1:]
            chunks = file_chunk_columns(columns, 1200)

            # Extract main table name from original filename
            main_table = file.filename.rsplit(".", 1)[0]
            schema = "realtime"

            with conn.cursor() as cur:
                pg_ensure_schema_and_metadata(cur, schema)
                for i, chunk in enumerate(chunks):
                    table = f"{main_table}_p{i + 1}"
                    pg_create_data_table(cur, schema, table, chunk, patient_col)
                    pg_insert_metadata(cur, schema, table, main_table, description, origin)
                    pg_insert_data_rows(cur, schema, table, patient_col, rows, chunk, i)

                conn.commit()

            # Invalidate metadata cache since new tables were created
            invalidate_metadata_cache()

            # Clean up temp file
            if temp_filepath and os.path.exists(temp_filepath):
                os.remove(temp_filepath)

            flash(f"Successfully uploaded {file.filename}", "success")
            return redirect(url_for("dashboard_routes.datasets"))

        except Exception as e:
            conn.rollback()
            current_app.logger.error(f"Upload failed: {e}")

            # Clean up temp file on error
            if temp_filepath and os.path.exists(temp_filepath):
                with contextlib.suppress(Exception):
                    os.remove(temp_filepath)

            raise GenericExceptionHandler(f"Upload failed: {str(e)}", status_code=400) from e

    return render_template("/dashboard/upload.html", user_email=user_email)


@routes.route("/display", methods=["GET", "POST"])
@login_required()
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

    if request.method == "GET" and search_term:
        search_column, _, _ = search_term

        data: list[TableNameResult] = supabase_extension.safe_rpc_call(
            "search_tables_by_column", {"search_column": search_column}
        )
        matching_tables = [(row["table_name"],) for row in data]

        results = {}
        total_rows = total_columns = 0

        for (table,) in matching_tables:
            columns_data: list[ColumnInfoResult] = get_cached_table_columns(table)
            columns = [row["column_name"] for row in columns_data]

            table_data: list[TableDataResult] = supabase_extension.safe_rpc_call(
                "select_from_table", {"p_table_name": table, "p_limit": 1000000}
            )

            # Convert JSONB data to tuples matching column order
            rows = []
            for row in table_data:
                row_data = row["data"]
                rows.append(tuple(row_data.get(col) for col in columns))

            if not rows:
                continue

            df = pd.DataFrame(rows, columns=columns)
            if not df.empty:
                df.drop(df.columns[0], axis=1, inplace=True)

            results[table] = df
            total_rows += len(rows)
            total_columns += len(columns)

        if not results:
            raise GenericExceptionHandler("No matching data found", status_code=404)

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
@login_required()
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

    if request.method == "GET":
        data: list[TableNameResult] = get_cached_tables()
        table_names = [row["table_name"] for row in data]

        return render_template(
            "/dashboard/search.html",
            table_names=table_names,
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

        search_data: list[TableNameResult] = supabase_extension.safe_rpc_call(
            "search_tables_by_column", {"search_column": search_term}
        )
        search_results = [row["table_name"] for row in search_data]

        all_tables_data: list[TableNameResult] = get_cached_tables()
        table_names = [row["table_name"] for row in all_tables_data]

        return render_template(
            "/dashboard/search.html",
            search_results=search_results,
            search_term=search_term,
            table_names=table_names,
            user_email=user_email,
            current_path=current_path,
        )


@routes.route("/update", methods=["GET", "POST"])
@login_required()
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

    if request.method == "POST":
        row_id = request.form.get("row_id")
        column_name = request.form.get("column_name")
        new_value = request.form.get("new_value")

        data: list[TableNameResult] = supabase_extension.safe_rpc_call(
            "search_tables_by_column", {"search_column": column_name}
        )
        tables = [row["table_name"] for row in data]

        if not tables:
            raise GenericExceptionHandler("No matching data found", status_code=404)

        for table in tables:
            supabase_extension.safe_rpc_call(
                "update_table_row",
                {
                    "p_table_name": table,
                    "p_row_id": int(row_id),
                    "p_updates": {column_name: new_value},
                },
            )

    return (
        render_template("/dashboard/update.html", user_email=user_email, current_path=request.path),
        200,
    )


@routes.route("/table_preview", methods=["GET", "POST"])
@login_required()
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

    if not table_name:
        raise GenericExceptionHandler(
            message="Table name is required",
            status_code=400,
        )

    table_exists: bool = supabase_extension.safe_rpc_call(
        "table_exists", {"p_table_name": table_name}
    )

    if not table_exists:
        raise GenericExceptionHandler(
            message=f"Table '{table_name}' not found in _realtime schema.",
            status_code=404,
        )

    columns_data: list[ColumnInfoResult] = get_cached_table_columns(table_name)
    columns = [row["column_name"] for row in columns_data]

    table_data: list[TableDataResult] = supabase_extension.safe_rpc_call(
        "select_from_table", {"p_table_name": table_name, "p_limit": 100}
    )

    # Convert JSONB data to tuples matching column order
    rows = []
    for row in table_data:
        row_data = row["data"]
        rows.append(tuple(row_data.get(col) for col in columns))

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

    tables_html = df_preview.to_html(classes="table table-bordered", header="true", index=False)

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
