import numpy as np
import pandas as pd


def compute_partition_by_ids(dataset: pd.DataFrame, quasi_cols: list) -> list:
    """
    Splits the dataset into equivalence groups based on
    quasi-identifying columns.

    :param dataset: A pandas DataFrame containing the dataset.
    :param quasi_cols: A list of column names considered as quasi-identifiers.
    :return: A list containing lists of row indices that form
    equivalence groups.
    """
    grouped = dataset.groupby(by=quasi_cols)
    partitions = [list(indices) for indices in grouped.groups.values()]
    return partitions


def get_group_key(quasi_cols: list, group_key: tuple) -> str:
    """
    Generate a readable key from quasi-identifiers and values.
    ---
    parameters:
      - name: quasi_cols
        in: body
        type: list
        required: true
        description: List of quasi-identifier column names.
      - name: group_key
        in: body
        type: tuple
        required: true
        description: Tuple of values for the group.
    returns:
      type: string
      description: Human-readable key like "col1: val1, col2: val2".
    """
    return ", ".join([f"{col}: {val}" for col, val in zip(quasi_cols, group_key, strict=False)])


def get_group_key_from_partition(df: pd.DataFrame, group_indices: list, quasi_cols: list) -> str:
    """
    Generate a group key based on the first row in the partition.
    ---
    parameters:
      - name: df
        in: body
        type: DataFrame
        required: true
        description: Full dataset.
      - name: group_indices
        in: body
        type: list
        required: true
        description: Row indices of the group.
      - name: quasi_cols
        in: body
        type: list
        required: true
        description: List of quasi-identifier column names.
    returns:
      type: string
      description: Formatted string key (e.g. 'col1: val1, col2: val2, ...').
    """
    group_df = df.iloc[group_indices]
    values = tuple(group_df.iloc[0][col] for col in quasi_cols)
    return get_group_key(quasi_cols, values)


def compute_categorical_t_closeness(df: pd.DataFrame, quasi_cols: list, sensitive_col: str) -> dict:
    """
    Compute t-closeness for categorical sensitive attributes.
    ---
    parameters:
      - name: df
        in: body
        type: DataFrame
        required: true
        description: Input dataset.
      - name: quasi_cols
        in: body
        type: list
        required: true
        description: List of quasi-identifier columns.
      - name: sensitive_col
        in: body
        type: string
        required: true
        description: The sensitive attribute to evaluate.
    returns:
      type: dict
      description: Mapping of group key to t-closeness score.
    """
    unique_vals = np.sort(df[sensitive_col].astype(str).unique())
    global_counts = (
        df[sensitive_col].value_counts(normalize=True).reindex(unique_vals, fill_value=0)
    )
    global_dist = global_counts.values

    partitions = compute_partition_by_ids(df, quasi_cols)
    group_t_scores = {}

    for group in partitions:
        subset = df.iloc[group]
        if subset.empty:
            continue
        group_counts = (
            subset[sensitive_col].value_counts(normalize=True).reindex(unique_vals, fill_value=0)
        )
        group_dist = group_counts.values
        t_score = 0.5 * np.sum(np.abs(group_dist - global_dist))

        group_key = get_group_key_from_partition(df, group, quasi_cols)
        group_t_scores[group_key] = t_score

    return group_t_scores


def compute_numeric_t_closeness(df: pd.DataFrame, quasi_cols: list, sensitive_col: str) -> dict:
    """
    Compute t-closeness for numeric sensitive attributes.
    ---
    parameters:
      - name: df
        in: body
        type: DataFrame
        required: true
        description: Input dataset.
      - name: quasi_cols
        in: body
        type: list
        required: true
        description: List of quasi-identifier columns.
      - name: sensitive_col
        in: body
        type: string
        required: true
        description: The sensitive attribute to evaluate.
    returns:
      type: dict
      description: Mapping of group key to t-closeness score.
    """
    unique_vals = np.sort(df[sensitive_col].unique())
    global_counts = (
        df[sensitive_col].value_counts(normalize=True).reindex(unique_vals, fill_value=0)
    )
    global_dist = global_counts.values

    partitions = compute_partition_by_ids(df, quasi_cols)
    group_t_scores = {}

    for group in partitions:
        subset = df.iloc[group]
        if subset.empty:
            continue
        group_counts = (
            subset[sensitive_col].value_counts(normalize=True).reindex(unique_vals, fill_value=0)
        )
        group_dist = group_counts.values
        t_score = 0.5 * np.sum(np.abs(group_dist - global_dist))

        group_key = get_group_key_from_partition(df, group, quasi_cols)
        group_t_scores[group_key] = t_score

    return group_t_scores


def compute_numeric_normalized_entropy(
    df: pd.DataFrame, quasi_cols: list, sensitive_col: str
) -> dict:
    """
    Compute normalized entropy for numeric sensitive attributes.
    ---
    parameters:
      - name: df
        in: body
        type: DataFrame
        required: true
        description: Input dataset.
      - name: quasi_cols
        in: body
        type: list
        required: true
        description: List of quasi-identifier columns.
      - name: sensitive_col
        in: body
        type: string
        required: true
        description: Sensitive attribute column name.
    returns:
      type: dict
      description: Mapping of group key to normalized entropy value (0–1).
    """
    partitions = compute_partition_by_ids(df, quasi_cols)
    total_rows = len(df)
    unique_vals = df[sensitive_col].nunique()

    if unique_vals <= 1 or total_rows == 0:
        return {}

    log_unique_vals = np.log2(unique_vals)
    group_ent_scores = {}

    for group in partitions:
        subset = df.iloc[group][sensitive_col]
        if subset.empty:
            continue
        probs = subset.value_counts(normalize=True).values
        ent = -np.sum(probs * np.log2(probs))
        group_key = get_group_key_from_partition(df, group, quasi_cols)
        group_ent_scores[group_key] = ent / log_unique_vals

    return group_ent_scores


def compute_categorical_normalized_entropy(
    df: pd.DataFrame, quasi_cols: list, sensitive_col: str
) -> dict:
    """
    Compute normalized entropy for categorical sensitive attributes.
    ---
    parameters:
      - name: df
        in: body
        type: DataFrame
        required: true
        description: Input dataset.
      - name: quasi_cols
        in: body
        type: list
        required: true
        description: List of quasi-identifier columns.
      - name: sensitive_col
        in: body
        type: string
        required: true
        description: Sensitive attribute column name.
    returns:
      type: dict
      description: Mapping of group key to normalized entropy value (0–1).
    """
    partitions = compute_partition_by_ids(df, quasi_cols)
    total_rows = len(df)
    unique_vals = df[sensitive_col].nunique()

    if unique_vals <= 1 or total_rows == 0:
        return {}

    log_unique_vals = np.log2(unique_vals)
    group_ent_scores = {}

    for group in partitions:
        subset = df.iloc[group]
        if subset.empty:
            continue
        val_counts = subset[sensitive_col].value_counts(normalize=True)
        ent = -sum(p * np.log2(p) for p in val_counts if p > 0)
        group_key = get_group_key_from_partition(df, group, quasi_cols)
        group_ent_scores[group_key] = ent / log_unique_vals

    return group_ent_scores


def compute_normalize_t_values(t_numeric):
    """
    Normalize t-closeness values per column (min-max).

    :param t_numeric: DataFrame containing numeric t-closeness values to
           be normalized.
    :type t_numeric: pd.DataFrame
    :return: A DataFrame with the normalized t-closeness values.
    :rtype: pd.DataFrame
    """
    t_normed = t_numeric.copy()
    for col in t_numeric.columns:
        col_min, col_max = t_numeric[col].min(), t_numeric[col].max()
        if col_max > col_min:
            t_normed[col] = (t_numeric[col] - col_min) / (col_max - col_min)
        else:
            t_normed[col] = 0.0
    return t_normed
