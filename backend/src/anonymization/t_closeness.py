import pandas as pd

from .utils.helpers import (
    compute_numeric_t_closeness,
    compute_categorical_t_closeness
)


def t_closeness_for_sensitive_attr(
    data: pd.DataFrame, quasi_ident: list, sens_attr: list
) -> pd.DataFrame:
    """
    Calculates the t-closeness value for each sensitive attribute.

    :param data: Input DataFrame.
    :param quasi_ident: List of quasi-identifier columns.
    :param sens_ident: List of sensitive-identifier columns.
    :return: Dictionary mapping each sensitive attribute to its
             t-closeness value.
    :rtype: dict.
    """
    t_overall = {}

    for sens_att_value in sens_attr:
        if pd.api.types.is_numeric_dtype(data[sens_att_value]):
            t_value = compute_numeric_t_closeness(
                data, quasi_ident, sens_att_value)
        else:
            t_value = compute_categorical_t_closeness(
                data, quasi_ident, sens_att_value)

        t_overall[sens_att_value] = t_value

    return pd.DataFrame.from_dict(t_overall)
