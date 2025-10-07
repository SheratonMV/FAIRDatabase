"""Functions for applying local differential privacy noise to data columns."""

import numpy as np


def add_randomized_response(value, categories, p=0.5):
    """
    Apply randomized response to a categorical value.
    ---
    tags:
      - differential-privacy
    parameters:
      - name: value
        type: string
        description: Original categorical value.
      - name: categories
        type: array
        description: List of unique categories in the column.
      - name: p
        type: number
        default: 0.5
        description: Probability to return the original value.
    returns:
      type: string
      description: Noisy value after applying randomized response.
    """
    if np.random.random() < p:
        return value
    return np.random.choice(categories)


def add_laplace_noise(column, sensitivity, epsilon):
    """
    Add Laplace noise to a numerical column.
    ---
    tags:
      - differential-privacy
    parameters:
      - name: column
        type: array
        description: Original numerical column (Pandas Series).
      - name: sensitivity
        type: number
        description: Sensitivity of the function applied to the column.
      - name: epsilon
        type: number
        description: Privacy budget parameter (ε).
    returns:
      type: array
      description: Noisy column after adding Laplace noise.
    """
    scale = sensitivity / epsilon
    noise = np.random.laplace(loc=0, scale=scale, size=column.shape)
    return column + noise


def add_noise_to_df(df, categorical_columns, numerical_columns, epsilon):
    """
    Add noise to a DataFrame based on local differential privacy.
    ---
    tags:
      - differential-privacy
    parameters:
      - name: df
        type: object
        description: Original DataFrame to modify.
      - name: categorical_columns
        type: array
        description: Names of columns treated as categorical.
      - name: numerical_columns
        type: array
        description: Names of columns treated as numerical.
      - name: epsilon
        type: number
        description: Privacy budget parameter (ε).
    returns:
      type: object
      description: Modified DataFrame with randomized and Laplace noise added.
    """
    noisy_df = df.copy()

    for column in numerical_columns:
        sensitivity = df[column].max() - df[column].min()
        noisy_df[column] = add_laplace_noise(df[column], sensitivity, epsilon)

    for column in categorical_columns:
        categories = df[column].unique()
        noisy_df[column] = df[column].apply(lambda x: add_randomized_response(x, categories))

    return noisy_df


def validate_column_selection(columns, categorical_cols, numerical_cols):
    """
    Validate that the selected categorical and numerical columns are correct.
    ---
    tags:
      - differential-privacy
    parameters:
      - name: columns
        type: array
        description: Complete list of all column names in the dataset.
      - name: categorical_cols
        type: array
        description: User-selected categorical columns.
      - name: numerical_cols
        type: array
        description: User-selected numerical columns.
    returns:
      type: boolean
      description: True if selection is valid and covers all columns with
                   no overlaps.
    """
    selected_cols = categorical_cols + numerical_cols
    return set(selected_cols) == set(columns) and (
        len(set(categorical_cols).intersection(numerical_cols)) == 0
    )
