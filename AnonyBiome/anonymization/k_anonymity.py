import pandas as pd

from .utils.helpers import compute_partition_by_ids, get_group_key


def k_anonymity_for_sensitive_attr(
    data: pd.DataFrame, quasi_idents: list
) -> pd.DataFrame:
    """
    Compute k-anonymity values for groups in the dataset.
    ---
    tags:
      - privacy
    parameters:
      - name: data
        required: true
        description: Input DataFrame to evaluate.
      - name: quasi_idents
        required: true
        description: List of quasi-identifier column names.
    returns:
      - type: DataFrame
        description: DataFrame with group keys and their k-anonymity values.
    """
    partitions = compute_partition_by_ids(data, quasi_idents)
    group_k_scores = {}

    for group in partitions:
        subset = data.iloc[group]
        group_key = get_group_key(subset.iloc[0], quasi_idents)
        group_k_scores[group_key] = len(subset)

    return pd.DataFrame.from_dict(
        group_k_scores, orient="index", columns=["k-anonymity"]
    )
