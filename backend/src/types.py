"""Type definitions for Supabase RPC function responses.

This module provides TypedDict classes that match the return types of RPC
functions defined in supabase/migrations/20250107000000_create_rpc_functions.sql
"""

from typing import TypedDict


class TableNameResult(TypedDict):
    """Return type for RPC functions that return table names.

    Used by:
    - get_all_tables()
    - search_tables_by_column()
    """
    table_name: str


class ColumnInfoResult(TypedDict):
    """Return type for get_table_columns() RPC function.

    Returns column metadata including name, data type, and nullability.
    """
    column_name: str
    data_type: str
    is_nullable: str


class TableDataResult(TypedDict):
    """Return type for select_from_table() RPC function.

    Returns JSONB data where each row is represented as a JSON object.
    The actual structure depends on the queried table's schema.
    """
    data: dict[str, str | int | float | bool | None]
