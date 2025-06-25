"""
Basic Usage Script.

This script loads a dataset and evaluates its privacy using k-anonymity,
l-diversity (via normalized entropy), and t-closeness metrics. It then filters
out records that do not meet privacy thresholds and computes a composite
privacy score (P(29)).
"""

import pandas as pd

from anonymization import (
    k_anonymity,
    normalized_entropy,
    p_29,
    t_closeness,
    enforce_privacy,
)


def main():
    filename = "df5.csv"
    df = pd.read_csv(filename)

    # Define quasi-identifiers and sensitive attributes
    quasi_identifiers = ["race", "gender", "age"]
    sensitive_attributes = [
        "diag_1",
        "diag_2",
        "diag_3",
        "max_glu_serum",
        "A1Cresult",
        "readmitted",
    ]

    # Step 1: Compute privacy metrics
    k_df = k_anonymity(df, quasi_identifiers)
    l_df = normalized_entropy(df, quasi_identifiers, sensitive_attributes)
    t_df = t_closeness(df, quasi_identifiers, sensitive_attributes)

    # Step 2: Enforce privacy thresholds
    clean_df = enforce_privacy(df, k_df, l_df, t_df, quasi_identifiers)

    # Step 3: Evaluate privacy using the P(29) score
    privacy_score = p_29(k_df, l_df, t_df)

    # Output
    print("P(29) Privacy Evaluation Report:")
    print(f"  Score: {privacy_score.score}")
    print(f"  Reasons for privacy risks: {privacy_score.reasons}")
    print(f"  Problematic groups info: {privacy_score.problematic_info}")
    print(f"  Minimum k-anonymity: {privacy_score.min_k}")
    print(f"  Minimum l-diversity: {privacy_score.min_l}")
    print(f"  Maximum t-closeness: {privacy_score.max_t}")
    print(f"  Normalized t-values:\n{privacy_score.t_numeric}")

    print(clean_df.head())


if __name__ == "__main__":
    main()
