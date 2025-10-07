"""
Privacy Evaluation Module.

This module provides utility functions to validate privacy guarantees based on
k-anonymity, l-diversity, and t-closeness principles. Each function evaluates
a specific privacy model and overall contributes to computing a combined
privacy assessment using the `validate_privacy` function.
"""

from collections import namedtuple

import pandas as pd

PrivEval = namedtuple(
    "PrivEval",
    ["score", "problematic_info", "reasons", "min_k", "min_l", "max_t", "t_numeric"],
)


def check_k_anonymity_violations(k_df: pd.DataFrame) -> tuple:
    """
    Check for k-anonymity violations.
    ---
    tags:
      - privacy
    parameters:
      - name: k_df
        required: true
        description: DataFrame of quasi-identifiers.
    returns:
      - type: boolean
        description: Whether any k-anonymity violations exist.
      - type: list
        description: List of violating row indices and reasons.
    """
    violations = []
    if k_df.min().min() <= 1:
        bad_rows = k_df[k_df == 1].dropna(how="all")
        violations = [(row, "k-anonymity is 1") for row in bad_rows.index]
        return True, violations
    return False, []


def check_l_diversity_violations(l_df: pd.DataFrame) -> tuple:
    """
    Check for l-diversity (normalized entropy) violations.
    ---
    tags:
      - privacy
    parameters:
      - name: l_df
        required: true
        description: DataFrame with normalized entropy values per quasi-identifier.
    returns:
      - type: boolean
        description: Whether any l-diversity violations exist.
      - type: list
        description: List of violating row indices and reasons.
    """
    violations = []
    has_issue = l_df.iloc[:, 1:].eq(0).any().any()
    if has_issue:
        for col in l_df.columns[1:]:
            zero_rows = l_df[l_df[col] == 0]
            violations.extend(
                [(row, f"normalized entropy l-value is 0 for {col}") for row in zero_rows.index]
            )
    return has_issue, violations


def check_t_closeness_violations(t_df: pd.DataFrame, threshold: float = 0.5) -> tuple:
    """
    Check for t-closeness violations.
    ---
    tags:
      - privacy
    parameters:
      - name: t_df
        required: true
        description: DataFrame with t-values for quasi-identifiers.
      - name: threshold
        required: false
        type: number
        default: 0.5
        description: Threshold for t-closeness violations.
    returns:
      - type: boolean
        description: Whether any t-closeness violations exist.
      - type: list
        description: List of violating row indices and reasons.
      - type: object
        description: DataFrame of numeric t-values.
    """
    violations = []
    t_numeric = t_df.apply(pd.to_numeric, errors="coerce")
    has_issue = (t_numeric > threshold).any().any()
    if has_issue:
        for col in t_numeric.columns:
            high_rows = t_df[t_numeric[col] > threshold]
            violations.extend(
                [(row, f"t-value exceeds {threshold} for {col}") for row in high_rows.index]
            )
    return has_issue, violations, t_numeric


def validate_privacy(
    k_df: pd.DataFrame,
    l_df: pd.DataFrame,
    t_df: pd.DataFrame,
) -> PrivEval:
    """
    Evaluate overall privacy using k-anonymity, l-diversity, and t-closeness.
    ---
    tags:
      - privacy
    parameters:
      - name: k_df
        required: true
        description: DataFrame with k-anonymity values.
      - name: l_df
        required: true
        description: DataFrame with l-diversity (normalized entropy) values.
      - name: t_df
        required: true
        description: DataFrame with t-closeness values.
    returns:
      - type: object
        description: Named tuple with privacy score, issues, and metrics.
    """
    reasons = []
    issues = []

    # --- k-anonymity check ---
    k_problem, k_issues = check_k_anonymity_violations(k_df)
    issues.extend(k_issues)
    if k_problem:
        reasons.append("k-anonymity is 1")

    # --- l-diversity check ---
    l_problem, l_issues = check_l_diversity_violations(l_df)
    issues.extend(l_issues)
    if l_problem:
        reasons.append("normalized entropy l-value is 0 for some attribute")

    # --- t-closeness check ---
    t_problem, t_issues, t_numeric = check_t_closeness_violations(t_df)
    issues.extend(t_issues)
    if t_problem:
        reasons.append("t-value exceeds 0.5 for some attribute")

    min_k = k_df.min().iloc[0]
    min_l = l_df.iloc[:, 1:].min().min()
    max_t = t_numeric.max().max()

    return PrivEval(
        score=0.0,
        problematic_info=issues,
        reasons=reasons,
        min_k=min_k,
        min_l=min_l,
        max_t=max_t,
        t_numeric=t_numeric,
    )
