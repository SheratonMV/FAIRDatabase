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
import json

from src.auth.decorators import login_required
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
        edge_function_url = "http://localhost:8000/functions/v1/get-dataset-stats"
        headers = {
            "Authorization": f"Bearer {current_app.config['SUPABASE_SERVICE_ROLE_KEY']}",
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
            error_message = f"Edge Function returned status {response.status_code}"
            flash(f"Could not load visualization data: {error_message}", "warning")

    except requests.exceptions.RequestException as e:
        error_message = str(e)
        flash(f"Could not connect to Edge Function: {error_message}", "warning")
        current_app.logger.error(f"Edge Function call failed: {e}")

    return (
        render_template(
            "/visualization/visualization.html",
            user_email=user_email,
            current_path=current_path,
            stats_data=stats_data,
            stats_json=json.dumps(stats_data) if stats_data else "null",
        ),
        200,
    )


@routes.route("/dataset/<table_name>")
@login_required()
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

    # check table exists
    if not validate_table_exists(conn, table_name):
        flash(f"Table '{table_name}' not found", "danger")
        return redirect(url_for('visualization_routes.visualization'))

    # get dataset statistics for the form
    stats_data = None
    try:
        edge_function_url = "http://localhost:8000/functions/v1/get-dataset-stats"
        headers = {
            "Authorization": f"Bearer {current_app.config['SUPABASE_SERVICE_ROLE_KEY']}",
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
        current_app.logger.error(f"Could not fetch stats data: {e}")

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
    except requests.exceptions.RequestException as e:
        error_message = str(e)
        flash(f"Could not connect to visualization service: {error_message}", "danger")
        current_app.logger.error(f"Connection error: {e}")
    except Exception as e:
        error_message = str(e)
        flash(f"Unexpected error: {error_message}", "danger")
        current_app.logger.error(f"Unexpected error: {e}")

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
            stats_json=json.dumps(stats_data) if stats_data else "null",
            viz_data=viz_data,
            viz_json=json.dumps(viz_data) if viz_data else "null",
            row_limit=row_limit,
            column_limit=column_limit,
            metric=metric,
            colorscale=colorscale,
            pseudocount=pseudocount,
            metadata=json.dumps(metadata_dict) if metadata_dict else "{}",
            metadata_fields=metadata_fields,
            has_metadata=has_meta,
        ),
        200,
    )
