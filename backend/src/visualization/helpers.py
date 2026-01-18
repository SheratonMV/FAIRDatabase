"""Helper functions for visualization module."""

import requests
from flask import current_app
from psycopg2 import sql


def call_visualization_edge_function(table_name, row_limit=50, column_limit=10, metric='bray_curtis', pseudocount=1.0):
    """
    Call Supabase Edge Function to generate visualization output.
    """
    edge_function_url = "http://localhost:8000/functions/v1/get-dataset-visualization"

    headers = {
        "Authorization": f"Bearer {current_app.config['SUPABASE_SERVICE_ROLE_KEY']}",
        "Content-Type": "application/json"
    }

    payload = {
        "table_name": table_name,
        "row_limit": row_limit,
        "column_limit": column_limit,
        "metric": metric,
        "pseudocount": pseudocount
    }

    response = requests.post(
        edge_function_url,
        headers=headers,
        json=payload,
        timeout=30
    )

    if response.status_code != 200:
        error_data = response.json() if response.headers.get('content-type') == 'application/json' else {}
        error_msg = error_data.get('error', f'HTTP {response.status_code}')
        raise ValueError(f"Edge Function error: {error_msg}")

    return response.json()


def validate_table_exists(conn, table_name):
    """
    validate if table exists in the _fd schema.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = '_fd'
                    AND table_name = %s
                )
                """,
                (table_name,)
            )
            result = cur.fetchone()
            return result[0] if result else False
    except Exception as e:
        current_app.logger.error(f"Error checking table existence: {e}")
        return False


def get_available_datasets(conn):
    """
    Get list of tables available for visualization.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = '_fd'
                AND table_name != 'metadata_tables'
                ORDER BY table_name
                """
            )

            tables = []
            for (table_name,) in cur.fetchall():
                # Get row count
                cur.execute(
                    sql.SQL("SELECT COUNT(*) FROM _fd.{}").format(
                        sql.Identifier(table_name)
                    )
                )
                row_count = cur.fetchone()[0]

                # Get column count (excluding rowid and patient column)
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.columns
                    WHERE table_schema = '_fd'
                    AND table_name = %s
                    AND column_name != 'rowid'
                    """,
                    (table_name,)
                )
                column_count = cur.fetchone()[0] - 1  # -1 for patient column

                tables.append({
                    'name': table_name,
                    'rows': row_count,
                    'columns': column_count
                })

            return tables
    except Exception as e:
        current_app.logger.error(f"Error getting available datasets: {e}")
        return []
