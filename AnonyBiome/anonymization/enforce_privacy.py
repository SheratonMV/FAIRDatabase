"""
Privacy enforcement Module.

Removes rows from the dataset where their group fails k-anonymity,
l-diversity, or t-closeness thresholds.

Returns a filtered DataFrame with only groups that meet all privacy criteria.
"""

import pandas as pd

from AnonyBiome.anonymization.k_anonymity import k_anonymity_for_sensitive_attr
from AnonyBiome.anonymization.t_closeness import t_closeness_for_sensitive_attr
from AnonyBiome.anonymization.normalized_entropy import (
    normalized_entropy_for_sensitive_attr,
)


def enforce_privacy(
    data: pd.DataFrame,
    quasi_idents: list[str],
    sens_attr: list[str],
    t_thresh: float = 0.5,
    k_thresh: int = 1,
    l_thresh: float = 0.0,
) -> pd.DataFrame:
    """
    Drop rows from groups violating k-anonymity, l-diversity, or t-closeness.
    ---
    tags:
      - privacy
    parameters:
      - name: df
        required: true
        description: Original input DataFrame.
      - name: k_df
        required: true
        description: DataFrame with 'k-anonymity' values.
      - name: l_df
        required: true
        description: DataFrame with l-diversity values.
      - name: t_df
        required: true
        description: DataFrame with t-closeness values.
      - name: quasi_ident
        required: true
        description: List of quasi-identifiers.
      - name: t_thresh
        type: number
        default: 0.5
        description: Max allowed t-closeness.
      - name: k_thresh
        type: integer
        default: 1
        description: Min required k-anonymity.
      - name: l_thresh
        type: number
        default: 0.0
        description: Min required l-diversity.
    returns:
      - type: DataFrame
        description: Filtered DataFrame with valid groups.
    """
    # --- Retrieve each module ---
    k_df = k_anonymity_for_sensitive_attr(data, quasi_idents)
    l_df = normalized_entropy_for_sensitive_attr(data, quasi_idents, sens_attr)
    t_df = t_closeness_for_sensitive_attr(data, quasi_idents, sens_attr)

    kl_df = k_df.merge(l_df, left_index=True, right_index=True)

    # --- Privacy checks ---
    k_ok = kl_df["k-anonymity"] > k_thresh

    l_vals = kl_df.drop(columns="k-anonymity").astype(float)
    l_ok = l_vals.gt(l_thresh).all(axis=1)

    t_vals = t_df.select_dtypes(include="number")
    t_ok = t_vals.le(t_thresh).all(axis=1)

    valid = k_ok & l_ok & t_ok
    invalid_keys = valid[~valid].index

    def get_key(row):
        return ", ".join(f"{col}: {row[col]}" for col in quasi_idents)

    keys = data.apply(get_key, axis=1)
    mask = ~keys.isin(invalid_keys)
    data_filtered = data[mask].copy()

    return data_filtered
