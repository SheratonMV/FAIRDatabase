import pandas as pd

from AnonyBiome.anonymization.utils.helpers import compute_normalize_t_values
from AnonyBiome.anonymization.checks.validators import validate_privacy, PrivEval
from AnonyBiome.anonymization.k_anonymity import k_anonymity_for_sensitive_attr
from AnonyBiome.anonymization.t_closeness import t_closeness_for_sensitive_attr
from AnonyBiome.anonymization.normalized_entropy import (
    normalized_entropy_for_sensitive_attr,
)


def P_29_score(
    data: pd.DataFrame,
    quasi_idents: list[str],
    sens_attr: list[str],
    w_k=0.5,
    w_l=0.25,
    w_t=0.25,
) -> PrivEval:
    """
    Compute P(29) privacy score using weighted k-anonymity, l-diversity, and
    t-closeness.
    ---
    tags:
      - privacy
    parameters:
      - name: k_df
        required: true
        description: DataFrame with k-anonymity values.
      - name: l_df
        required: true
        description: DataFrame with l-diversity (entropy) values.
      - name: t_df
        required: true
        description: DataFrame with t-closeness values.
      - name: w_k
        type: number
        default: 0.5
        description: Weight for k-anonymity.
      - name: w_l
        type: number
        default: 0.25
        description: Weight for l-diversity.
      - name: w_t
        type: number
        default: 0.25
        description: Weight for t-closeness.
    returns:
      - type: object
        description: Named tuple with score, reasons, and privacy metrics.
    """
    # --- Retrieve each module ---
    k_df = k_anonymity_for_sensitive_attr(data, quasi_idents)
    l_df = normalized_entropy_for_sensitive_attr(data, quasi_idents, sens_attr)
    t_df = t_closeness_for_sensitive_attr(data, quasi_idents, sens_attr)

    # --- Retrieve Privacy Evaluation information ---
    privEval: PrivEval = validate_privacy(k_df, l_df, t_df)

    t_numeric = privEval.t_numeric
    min_k = privEval.min_k

    if privEval.reasons:
        return privEval._replace(score=0.0)

    # --- Normalize remaining values ---
    normalized_l = l_df.select_dtypes(include="number").mean().mean()
    normalized_t = compute_normalize_t_values(t_numeric).mean().mean()

    # --- Compute final score ---
    score = w_k * (1 - (1 / min_k)) + w_l * normalized_l + w_t * (1 - normalized_t)

    privEval = privEval._replace(score=score)

    return privEval
