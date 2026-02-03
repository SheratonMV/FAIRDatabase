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
    )

from .helpers import (
    pg_ensure_schema_and_metadata,
    pg_create_data_table,
    pg_insert_metadata,
    pg_insert_data_rows,
    file_chunk_columns,
    file_save_and_read,
)

from config import Error
from src.exceptions import GenericExceptionHandler
from src.auth.decorators import login_required
from io import BytesIO
from psycopg2 import sql


import os
import zipfile
import pandas as pd

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

        try:
            description = request.form.get("description", "")
            origin = request.form.get("origin", "")
            lines, filename = file_save_and_read(file)
            header, rows = lines[0], lines[1:]
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
                        cur, schema, table, main_table, description, origin
                    )
                    pg_insert_data_rows(cur, schema, table,
                                        patient_col, rows, chunk, i)

            conn.commit()

            os.remove(os.path.join(
                current_app.config["UPLOAD_FOLDER"], filename))

            # show that it is uploaded succesfully
            flash(f"Dataset '{main_table}' uploaded successfully! {len(chunks)} table(s) created.", "success")
            return redirect(url_for("dashboard_routes.upload"))

        except Exception as e:
            conn.rollback()
            print(e)
            raise GenericExceptionHandler(
                f"Upload failed: {str(e)}", status_code=400)

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
                matching_tables = cur.fetchall()
        except Error as e:
            conn.rollback()
            raise GenericExceptionHandler(
                f"Schema query failed: {str(e)}", status_code=500
            )

        results = {}
        total_rows = total_columns = 0

        for (table,) in matching_tables:
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

            except Error as e:
                conn.rollback()
                raise GenericExceptionHandler(
                    f"Schema query failed: {str(e)}", status_code=500
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

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT table_name
                    FROM information_schema.tables
                    WHERE table_schema = '_fd';
                """
                )
                table_names = [row[0] for row in cur.fetchall()]

        except Error as e:
            conn.rollback()
            raise GenericExceptionHandler(
                f"Failed to fetch rows: {str(e)}", status_code=500
            )

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
    conn = g.db

    if request.method == "POST":
        row_id = request.form.get("row_id")
        column_name = request.form.get("column_name")
        new_value = request.form.get("new_value")

        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT DISTINCT table_name
                    FROM information_schema.columns
                    WHERE column_name ILIKE %s
                    AND table_schema = '_fd';
                    """,
                    (f"%{column_name}%",),
                )
            except Error as e:
                conn.rolback()
                raise GenericExceptionHandler(
                    f"Failed to select rows: {str(e)}", status_code=500
                )

            tables = [row[0] for row in cur.fetchall()]

            if not tables:
                raise GenericExceptionHandler(
                    "No matching data found", status_code=404)

            try:
                for table in tables:
                    cur.execute(
                        sql.SQL("UPDATE {}.{} SET {} = %s WHERE rowid = %s").format(
                            sql.Identifier("_fd"),
                            sql.Identifier(table),
                            sql.Identifier(column_name),
                        ),
                        (new_value, row_id),
                    )

            except Error as e:
                conn.rollback()
                raise GenericExceptionHandler(
                    f"Failed to update rows: {str(e)}", status_code=500
                )

        conn.commit()

    return (
        render_template(
            "/dashboard/update.html", user_email=user_email, current_path=request.path
        ),
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
    conn = g.db

    if not table_name:
        raise GenericExceptionHandler(
            message="Table name is required",
            status_code=400,
        )

    try:
        with conn.cursor() as cur:
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

    except Error as e:
        conn.rollback()
        raise GenericExceptionHandler(
            message=f"Error fetching table information: {str(e)}",
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

        except Error as e:
            conn.rollback()
            raise GenericExceptionHandler(
                message=f"Error selecting data: {str(e)}",
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
