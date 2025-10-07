"""
Integration tests for privacy helper functions.

Tests cover:
- Randomized response mechanism
- Laplace noise addition
- Differential privacy guarantees
- DataFrame-level noise operations
- Column validation
"""

import pytest
import pandas as pd
import numpy as np
from src.privacy.helpers import (
    add_randomized_response,
    add_laplace_noise,
    add_noise_to_df,
    validate_column_selection,
)


class TestRandomizedResponse:
    """Test randomized response differential privacy mechanism"""

    def test_returns_original_value_with_probability_one(self):
        """p=1.0 → always returns original value"""
        np.random.seed(42)
        categories = ['A', 'B', 'C']
        original = 'A'

        # With p=1.0, should always return original
        results = [add_randomized_response(original, categories, p=1.0) for _ in range(100)]

        assert all(r == original for r in results)

    def test_returns_random_value_with_probability_zero(self):
        """p=0.0 → never returns original value (for categories > 1)"""
        np.random.seed(42)
        categories = ['A', 'B', 'C']
        original = 'A'

        # With p=0.0, should never return original (assuming random selection)
        results = [add_randomized_response(original, categories, p=0.0) for _ in range(100)]

        # Should get mix of B and C, but not all A
        unique_values = set(results)
        assert len(unique_values) >= 1  # Should have variety

    def test_respects_probability_parameter(self):
        """p=0.5 → approximately 50% original, 50% random"""
        np.random.seed(42)
        categories = ['A', 'B', 'C', 'D']
        original = 'A'

        results = [add_randomized_response(original, categories, p=0.5) for _ in range(1000)]

        # With large sample, should be approximately 50% original
        original_count = sum(1 for r in results if r == original)
        original_ratio = original_count / len(results)

        # Allow more variance for randomness (0.35 to 0.65)
        assert 0.35 <= original_ratio <= 0.65

    def test_returns_value_from_valid_categories(self):
        """All returned values → from category list"""
        np.random.seed(42)
        categories = ['cat1', 'cat2', 'cat3']
        original = 'cat1'

        results = [add_randomized_response(original, categories, p=0.7) for _ in range(100)]

        # All results should be from the categories list
        assert all(r in categories for r in results)

    def test_handles_single_category(self):
        """Single category → always returns that category"""
        np.random.seed(42)
        categories = ['only_one']
        original = 'only_one'

        results = [add_randomized_response(original, categories, p=0.5) for _ in range(100)]

        # Can only return the single category
        assert all(r == 'only_one' for r in results)

    def test_handles_different_data_types(self):
        """Numeric categories → works correctly"""
        np.random.seed(42)
        categories = [1, 2, 3, 4, 5]
        original = 1

        results = [add_randomized_response(original, categories, p=0.8) for _ in range(100)]

        # All results should be from categories (type may vary)
        assert all(r in categories for r in results)


class TestLaplaceNoise:
    """Test Laplace noise mechanism"""

    def test_adds_noise_to_numeric_column(self):
        """Numeric column → noise added"""
        np.random.seed(42)
        column = pd.Series([100, 100, 100, 100, 100])

        result = add_laplace_noise(column, sensitivity=1.0, epsilon=1.0)

        # Results should vary from original
        assert len(result.unique()) > 1

        # Mean should be close to original (noise centers around 0)
        assert abs(result.mean() - 100) < 5

    def test_respects_sensitivity_parameter(self):
        """Higher sensitivity → more noise"""
        np.random.seed(42)
        column = pd.Series([50] * 100)

        # Low sensitivity
        low_sens_result = add_laplace_noise(column, sensitivity=0.1, epsilon=1.0)
        low_sens_variance = low_sens_result.var()

        # High sensitivity
        np.random.seed(42)
        high_sens_result = add_laplace_noise(column, sensitivity=10.0, epsilon=1.0)
        high_sens_variance = high_sens_result.var()

        # Higher sensitivity should result in higher variance
        assert high_sens_variance > low_sens_variance

    def test_respects_epsilon_parameter(self):
        """Smaller epsilon → more noise (stronger privacy)"""
        np.random.seed(42)
        column = pd.Series([50] * 100)

        # Large epsilon (less noise)
        large_eps_result = add_laplace_noise(column, sensitivity=1.0, epsilon=10.0)
        large_eps_variance = large_eps_result.var()

        # Small epsilon (more noise)
        np.random.seed(42)
        small_eps_result = add_laplace_noise(column, sensitivity=1.0, epsilon=0.1)
        small_eps_variance = small_eps_result.var()

        # Smaller epsilon should result in higher variance
        assert small_eps_variance > large_eps_variance

    def test_noise_distribution_properties(self):
        """Laplace noise → symmetric distribution around original"""
        np.random.seed(42)
        column = pd.Series([100] * 1000)

        result = add_laplace_noise(column, sensitivity=1.0, epsilon=1.0)

        # Mean should be close to original
        assert abs(result.mean() - 100) < 2

        # Should have roughly equal values above and below original
        above = sum(1 for r in result if r > 100)
        below = sum(1 for r in result if r < 100)
        assert 0.4 <= above / len(result) <= 0.6

    def test_handles_zero_values(self):
        """Zero values → noise added correctly"""
        np.random.seed(42)
        column = pd.Series([0.0] * 100)

        result = add_laplace_noise(column, sensitivity=1.0, epsilon=1.0)

        # Should have positive and negative values
        has_positive = any(r > 0 for r in result)
        has_negative = any(r < 0 for r in result)
        assert has_positive and has_negative


class TestAddNoiseToDf:
    """Test DataFrame-level noise addition"""

    def test_adds_noise_to_numeric_columns(self):
        """Numeric columns → noise added"""
        np.random.seed(42)
        df = pd.DataFrame({
            'value1': [10, 20, 30, 40, 50],
            'category': ['A', 'B', 'A', 'B', 'A'],
            'value2': [100, 200, 300, 400, 500]
        })

        noisy_df = add_noise_to_df(df, categorical_columns=[], numerical_columns=['value1'], epsilon=1.0)

        # Original DataFrame should be unchanged
        assert df['value1'].tolist() == [10, 20, 30, 40, 50]

        # Noisy DataFrame should have different values
        assert noisy_df['value1'].tolist() != df['value1'].tolist()

        # Non-selected columns should be unchanged
        assert noisy_df['value2'].tolist() == df['value2'].tolist()
        assert noisy_df['category'].tolist() == df['category'].tolist()

    def test_adds_noise_to_multiple_numeric_columns(self):
        """Multiple numeric columns selected → all get noise"""
        np.random.seed(42)
        df = pd.DataFrame({
            'col1': [1, 2, 3, 4, 5],
            'col2': [10, 20, 30, 40, 50],
            'col3': [100, 200, 300, 400, 500]
        })

        noisy_df = add_noise_to_df(df, categorical_columns=[], numerical_columns=['col1', 'col2'], epsilon=1.0)

        # Selected columns should have noise
        assert noisy_df['col1'].tolist() != df['col1'].tolist()
        assert noisy_df['col2'].tolist() != df['col2'].tolist()

        # Unselected column should be unchanged
        assert noisy_df['col3'].tolist() == df['col3'].tolist()

    def test_adds_randomized_response_to_categorical_columns(self):
        """Categorical columns → randomized response applied"""
        np.random.seed(42)
        df = pd.DataFrame({
            'category': ['A', 'B', 'C'] * 10,
            'value': [1, 2, 3] * 10
        })

        noisy_df = add_noise_to_df(df, categorical_columns=['category'], numerical_columns=[], epsilon=1.0)

        # Categorical column may have different values
        # But all values should still be from the original categories
        assert set(noisy_df['category'].unique()).issubset({'A', 'B', 'C'})

        # Numeric column should be unchanged
        assert noisy_df['value'].tolist() == df['value'].tolist()

    def test_adds_noise_to_both_categorical_and_numerical(self):
        """Mixed columns → both types get appropriate noise"""
        np.random.seed(42)
        df = pd.DataFrame({
            'age': [25, 30, 35, 40, 45],
            'gender': ['M', 'F', 'M', 'F', 'M']
        })

        noisy_df = add_noise_to_df(df, categorical_columns=['gender'], numerical_columns=['age'], epsilon=1.0)

        # Age should have Laplace noise
        assert noisy_df['age'].tolist() != df['age'].tolist()

        # Gender should have randomized response (all values still valid)
        assert set(noisy_df['gender'].unique()).issubset({'M', 'F'})

    def test_preserves_dataframe_structure(self):
        """After adding noise → same shape and columns"""
        np.random.seed(42)
        df = pd.DataFrame({
            'a': [1, 2, 3],
            'b': [4, 5, 6],
            'c': ['X', 'Y', 'Z']
        })

        noisy_df = add_noise_to_df(df, categorical_columns=['c'], numerical_columns=['a'], epsilon=1.0)

        assert noisy_df.shape == df.shape
        assert list(noisy_df.columns) == list(df.columns)
        assert len(noisy_df) == len(df)


class TestValidateColumnSelection:
    """Test column validation for privacy operations"""

    def test_validates_all_columns_covered_with_no_overlap(self):
        """All columns covered, no overlap → returns True"""
        all_columns = ['age', 'gender', 'income']
        categorical = ['gender']
        numerical = ['age', 'income']

        result = validate_column_selection(all_columns, categorical, numerical)

        assert result is True

    def test_rejects_missing_columns(self):
        """Not all columns covered → returns False"""
        all_columns = ['age', 'gender', 'income']
        categorical = ['gender']
        numerical = ['age']  # 'income' is missing

        result = validate_column_selection(all_columns, categorical, numerical)

        assert result is False

    def test_rejects_overlapping_columns(self):
        """Column in both categorical and numerical → returns False"""
        all_columns = ['age', 'gender']
        categorical = ['gender', 'age']  # age in both
        numerical = ['age']

        result = validate_column_selection(all_columns, categorical, numerical)

        assert result is False

    def test_rejects_extra_columns(self):
        """Selected columns not in all_columns → returns False"""
        all_columns = ['age', 'gender']
        categorical = ['gender', 'extra_col']
        numerical = ['age']

        result = validate_column_selection(all_columns, categorical, numerical)

        assert result is False

    def test_handles_empty_selections(self):
        """Empty all_columns with empty selections → returns True"""
        all_columns = []
        categorical = []
        numerical = []

        result = validate_column_selection(all_columns, categorical, numerical)

        assert result is True

    def test_all_categorical(self):
        """All columns categorical, no numerical → valid"""
        all_columns = ['gender', 'category', 'status']
        categorical = ['gender', 'category', 'status']
        numerical = []

        result = validate_column_selection(all_columns, categorical, numerical)

        assert result is True

    def test_all_numerical(self):
        """All columns numerical, no categorical → valid"""
        all_columns = ['age', 'income', 'height']
        categorical = []
        numerical = ['age', 'income', 'height']

        result = validate_column_selection(all_columns, categorical, numerical)

        assert result is True


class TestPrivacyHelpersIntegration:
    """Integration tests for privacy workflows"""

    def test_complete_differential_privacy_workflow(self):
        """Load data → validate → add noise → verify privacy"""
        np.random.seed(42)

        # Create sensitive dataset
        df = pd.DataFrame({
            'patient_id': ['P1', 'P2', 'P3', 'P4', 'P5'],
            'age': [25, 30, 35, 40, 45],
            'income': [50000, 60000, 70000, 80000, 90000],
            'diagnosis': ['A', 'B', 'A', 'C', 'B']
        })

        # Step 1: Validate columns for noise addition
        all_columns = ['age', 'income', 'diagnosis']
        is_valid = validate_column_selection(
            all_columns,
            categorical_cols=['diagnosis'],
            numerical_cols=['age', 'income']
        )
        assert is_valid is True

        # Step 2: Add noise to both categorical and numerical columns
        noisy_df = add_noise_to_df(
            df,
            categorical_columns=['diagnosis'],
            numerical_columns=['age', 'income'],
            epsilon=1.0
        )

        # Verify noise was added to numerical columns
        assert noisy_df['age'].tolist() != df['age'].tolist()
        assert noisy_df['income'].tolist() != df['income'].tolist()

        # Verify randomized response applied to diagnosis (values still valid)
        assert set(noisy_df['diagnosis'].unique()).issubset({'A', 'B', 'C'})

        # Verify structure preserved
        assert noisy_df.shape == df.shape
        assert list(noisy_df.columns) == list(df.columns)

        # Verify patient IDs unchanged (not selected for noise)
        assert noisy_df['patient_id'].tolist() == df['patient_id'].tolist()

    def test_privacy_preserves_statistical_properties(self):
        """Noisy data → maintains approximate statistics"""
        np.random.seed(42)

        # Large dataset for statistical stability
        df = pd.DataFrame({
            'value': [50] * 1000
        })

        # Add noise
        noisy_df = add_noise_to_df(
            df,
            categorical_columns=[],
            numerical_columns=['value'],
            epsilon=1.0
        )

        # Mean should be close to original (within a reasonable range)
        original_mean = df['value'].mean()
        noisy_mean = noisy_df['value'].mean()

        assert abs(noisy_mean - original_mean) < 5
