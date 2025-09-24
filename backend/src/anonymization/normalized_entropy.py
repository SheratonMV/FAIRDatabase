import pandas as pd

from .utils.helpers import (
    compute_numeric_normalized_entropy,
    compute_categorical_normalized_entropy,
)


def normalized_entropy_for_sensitive_attr(
    data: pd.DataFrame, quasi_ident: list, sens_ident: list
) -> pd.DataFrame:
    """
    Calculate t-closeness value for sensitive attributes.
    ---
    tags:
      - privacy
    parameters:
      - name: data
        required: true
        description: Input DataFrame.
      - name: quasi_ident
        required: true
        description: List of quasi-identifier columns.
      - name: sens_ident
        required: true
        description: List of sensitive-identifier columns.
    returns:
      - type: DataFrame
        description: Dictionary mapping each sensitive attribute to its t-closeness value.
    """
    ent_overall = {}

    for sens_att_value in sens_ident:
        if pd.api.types.is_numeric_dtype(data[sens_att_value]):
            ent_vals = compute_numeric_normalized_entropy(
                data, quasi_ident, sens_att_value
            )

        else:
            ent_vals = compute_categorical_normalized_entropy(
                data, quasi_ident, sens_att_value
            )

        ent_overall[sens_att_value] = ent_vals
    
    return pd.DataFrame.from_dict(ent_overall)
