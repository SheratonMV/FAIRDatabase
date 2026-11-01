"""Flask routes for visualizations"""

from flask import (
    render_template,
    session,
    request,
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    url_for,
)
import requests

from src.auth.decorators import login_required
from src.dashboard.helpers import assert_can_read_table
from .helpers import (
    call_visualization_edge_function,
    validate_table_exists,
    get_available_datasets
)

routes = Blueprint("visualization_routes", __name__)


@routes.route("/")
@login_required()
def visualization():
    """
    Main visualization page for exploratory data analysis.
    """
    user_email = session.get("email", "")
    current_path = request.path
    stats_data = None
    error_message = None

    try:
        # call the Supabase Edge Function
        service_key = current_app.config['SUPABASE_SERVICE_ROLE_KEY']
        edge_function_url = f"{current_app.config.get('SUPABASE_URL', 'http://localhost:8000')}/functions/v1/get-dataset-stats"
        headers = {
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "application/json"
        }

        response = requests.post(
            edge_function_url,
            headers=headers,
            json={},
            timeout=10
        )

        if response.status_code == 200:
            stats_data = response.json()
        else:
            current_app.logger.warning(f"Edge Function returned status {response.status_code}")

    except requests.exceptions.RequestException as e:
        current_app.logger.warning(f"Edge Function call failed: {e}")

    # Fallback: query DB directly if edge function failed
    if not stats_data:
        try:
            tables = get_available_datasets(g.db)
            if tables:
                stats_data = {
                    "success": True,
                    "tables": tables,
                    "summary": {
                        "total_datasets": len(tables),
                        "total_rows": sum(t["rows"] for t in tables),
                        "total_columns": sum(t["columns"] for t in tables),
                        "avg_rows": round(sum(t["rows"] for t in tables) / len(tables)) if tables else 0,
                    },
                    "metadata": [],
                }
        except Exception as e:
            current_app.logger.error(f"DB fallback also failed: {e}")

    if not stats_data:
        flash("No datasets available. Please upload some data first.", "info")

    return (
        render_template(
            "/visualization/visualization.html",
            user_email=user_email,
            current_path=current_path,
            stats_data=stats_data,
            # Passed as objects; the template serialises them with |tojson,
            # which escapes "<" so a value such as "</script>" in a dataset
            # description or metadata cell cannot break out of the script.
        ),
        200,
    )


@routes.route("/dataset/<table_name>")
@login_required("admin", "curator", "accessor")
def dataset_visualization(table_name):
    """
    Generate beta diversity visualization for a specific dataset.
    """
    user_email = session.get("email", "")
    current_path = request.path
    conn = g.db

    # get parameter form input users
    row_limit = request.args.get('row_limit', 50, type=int)
    column_limit = request.args.get('column_limit', 10, type=int)
    metric = request.args.get('metric', 'bray_curtis', type=str)
    colorscale = request.args.get('colorscale', 'Viridis', type=str)
    pseudocount = request.args.get('pseudocount', 1.0, type=float)

    # check if limit is ok
    if row_limit > 10000 or row_limit < 1:
        flash("Row limit must be between 1 and 10000", "warning")
        return redirect(url_for('visualization_routes.visualization'))

    if column_limit > 200 or column_limit < 2:
        flash("Column limit must be between 2 and 200", "warning")
        return redirect(url_for('visualization_routes.visualization'))

    # check the metric
    if metric not in ['bray_curtis', 'aitchison']:
        flash("Invalid metric. Must be 'bray_curtis' or 'aitchison'", "warning")
        return redirect(url_for('visualization_routes.visualization'))

    # check colorscale
    valid_colorscales = ['Viridis', 'Cividis', 'Magma']
    if colorscale not in valid_colorscales:
        flash("Invalid colorscale", "warning")
        return redirect(url_for('visualization_routes.visualization'))

    # check pseudocount
    valid_pseudocounts = [0.001, 0.01, 0.1, 0.5, 1.0]
    if pseudocount not in valid_pseudocounts:
        flash("Invalid pseudocount. Must be 0.001, 0.01, 0.1, 0.5, or 1.0", "warning")
        return redirect(url_for('visualization_routes.visualization'))

    # This page plots every sample of one dataset and shows its per-sample
    # metadata, so the caller must own the dataset or hold a grant on it.
    # The edge function below is called with the service key, which skips
    # its own per-user check, so this is the gate that counts. A refused
    # table gets the same "not found" as a missing one, so users cannot
    # probe which datasets exist.
    try:
        with conn.cursor() as cur:
            assert_can_read_table(cur, table_name, g.user, g.role)
        table_exists = validate_table_exists(conn, table_name)
    except PermissionError:
        table_exists = False
    if not table_exists:
        flash(f"Table '{table_name}' not found", "danger")
        return redirect(url_for('visualization_routes.visualization'))

    # get dataset statistics for the form
    stats_data = None
    try:
        service_key = current_app.config['SUPABASE_SERVICE_ROLE_KEY']
        edge_function_url = f"{current_app.config.get('SUPABASE_URL', 'http://localhost:8000')}/functions/v1/get-dataset-stats"
        headers = {
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "application/json"
        }

        stats_response = requests.post(
            edge_function_url,
            headers=headers,
            json={},
            timeout=10
        )

        if stats_response.status_code == 200:
            stats_data = stats_response.json()
    except Exception as e:
        current_app.logger.warning(f"Could not fetch stats from edge function: {e}")

    # Fallback: query DB directly if edge function failed
    if not stats_data:
        try:
            tables = get_available_datasets(conn)
            if tables:
                stats_data = {
                    "success": True,
                    "tables": tables,
                    "summary": {
                        "total_datasets": len(tables),
                        "total_rows": sum(t["rows"] for t in tables),
                        "total_columns": sum(t["columns"] for t in tables),
                        "avg_rows": round(sum(t["rows"] for t in tables) / len(tables)) if tables else 0,
                    },
                    "metadata": [],
                }
        except Exception as e:
            current_app.logger.error(f"DB fallback also failed: {e}")

    # call Edge Function to get visualization data
    viz_data = None
    error_message = None

    try:
        viz_data = call_visualization_edge_function(
            table_name,
            row_limit,
            column_limit,
            metric,
            pseudocount
        )

        if not viz_data.get('success'):
            error_message = viz_data.get('error', 'Unknown error')
            flash(f"Visualization generation failed: {error_message}", "danger")
            viz_data = None

    except ValueError as e:
        error_message = str(e)
        flash(f"Error generating visualization: {error_message}", "danger")
        current_app.logger.error(f"Edge Function error: {e}")
    except requests.exceptions.RequestException:
        error_message = "visualization service unreachable"
        flash("Could not connect to the visualization service.", "danger")
        current_app.logger.exception("visualization edge function unreachable")
    except Exception:
        error_message = "unexpected error"
        flash("Unexpected error while generating the visualization.", "danger")
        current_app.logger.exception("visualization failed")

    # Get metadata if available
    from src.data.metadata_helpers import get_metadata, get_metadata_fields, has_metadata
    metadata_dict = {}
    metadata_fields = []
    has_meta = False
    try:
        has_meta = has_metadata(table_name, conn)
        if has_meta:
            metadata_dict = get_metadata(table_name, conn)
            metadata_fields = get_metadata_fields(table_name, conn)
    except:
        pass

    return (
        render_template(
            "/visualization/visualization.html",
            user_email=user_email,
            current_path=current_path,
            table_name=table_name,
            stats_data=stats_data,
            # Passed as objects; the template serialises them with |tojson,
            # which escapes "<" so a value such as "</script>" in a dataset
            # description or metadata cell cannot break out of the script.
            viz_data=viz_data,
            row_limit=row_limit,
            column_limit=column_limit,
            metric=metric,
            colorscale=colorscale,
            pseudocount=pseudocount,
            metadata=metadata_dict or {},
            metadata_fields=metadata_fields,
            has_metadata=has_meta,
        ),
        200,
    )
