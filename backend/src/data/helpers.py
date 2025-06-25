"""Utility functions for file validation, dataframe preprocessing,
   and data generalization mappings."""

from config import Config


def allowed_file(filename):
    """
    Check if the uploaded file has a valid extension.
    ---
    tags:
      - utils
    parameters:
      - name: filename
        in: formData
        type: string
        required: true
        description: Name of the uploaded file.
    responses:
      200:
        description: Returns true if file has allowed extension (.csv).
    """
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS
    )


def drop_columns(df, columns_to_drop):
    """
    Drop specified columns from a dataframe.
    ---
    tags:
      - preprocessing
    parameters:
      - name: df
        in: body
        type: object
        required: true
        description: DataFrame from which columns will be dropped.
      - name: columns_to_drop
        in: body
        type: array
        items:
          type: string
        required: true
        description: List of column names to drop.
    responses:
      200:
        description: Returns true if columns were dropped successfully.
      400:
        description: Returns false if operation failed.
    """
    try:
        df.drop(columns=columns_to_drop, inplace=True, errors="ignore")
        return True
    except Exception:
        return False


def calculate_missing_percentages(df):
    """
    Calculate percentage of missing values in each column.
    ---
    tags:
      - preprocessing
    parameters:
      - name: df
        in: body
        type: object
        required: true
        description: DataFrame to analyze.
    responses:
      200:
        description: Dictionary of column names mapped to percentage of missing values.
    """
    return (df.isnull().sum() / len(df) * 100).round(2).to_dict()


def identify_quasi_identifiers_with_distinct_values(df, quasi_identifiers):
    """
    Identify distinct values and prepare mapping placeholders for quasi-identifiers.
    ---
    tags:
      - generalization
    parameters:
      - name: df
        in: body
        type: object
        required: true
        description: DataFrame containing the quasi-identifiers.
      - name: quasi_identifiers
        in: body
        type: array
        items:
          type: string
        required: true
        description: List of column names considered as quasi-identifiers.
    responses:
      200:
        description: Returns tuple of (distinct_values_dict, initial_mapping_dict).
    """
    distinct_values = {}
    mappings = {}
    for col in quasi_identifiers:
        unique_values = df[col].dropna().astype(str).unique().tolist()
        distinct_values[col] = unique_values
        mappings[col] = {}
    return distinct_values, mappings


def map_values_and_output_percentages(df, columns, mappings):
    """
    Apply value mappings to quasi-identifiers and return updated distributions.
    ---
    tags:
      - generalization
    parameters:
      - name: df
        in: body
        type: object
        required: true
        description: DataFrame containing columns to be generalized.
      - name: columns
        in: body
        type: array
        items:
          type: string
        required: true
        description: Columns to which mappings will be applied.
      - name: mappings
        in: body
        type: object
        required: true
        description: Nested dictionary of mappings {column: {original: mapped}}.
    responses:
      200:
        description: Tuple of updated DataFrame and mapping summary {column: {mapped_value: percentage}}.
    """
    result = {}
    for col in columns:
        if col not in df.columns or col not in mappings:
            continue
        mapping = mappings[col]
        df[col] = df[col].astype(str).map(mapping).fillna(df[col])
        value_counts = df[col].value_counts(normalize=True) * 100
        result[col] = value_counts.round(2).to_dict()
    return df, result
