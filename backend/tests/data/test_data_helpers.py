"""
Integration tests for data helper functions.

Tests cover:
- File extension validation
- Column operations
- Missing value calculations
- Quasi-identifier detection
- Value mapping and statistics
"""

import numpy as np
import pandas as pd
import pytest

from src.data.helpers import (
    allowed_file,
    calculate_missing_percentages,
    drop_columns,
    identify_quasi_identifiers_with_distinct_values,
    map_values_and_output_percentages,
)


class TestAllowedFile:
    """Test file extension validation"""

    @pytest.mark.parametrize(
        "filename,expected",
        [
            # Valid CSV files
            ("data.csv", True),
            ("dataset.csv", True),
            ("my_file.csv", True),
            # Case variations
            ("data.CSV", True),
            ("data.Csv", True),
            ("data.CsV", True),
            # Multiple dots
            ("data.backup.csv", True),
            ("file.v2.csv", True),
            ("archive.2024.01.01.csv", True),
            # Invalid extensions
            ("data.txt", False),
            ("data.xlsx", False),
            ("data.json", False),
            ("data.xls", False),
            # Edge cases
            ("data", False),  # No extension
            (".csv", True),  # Hidden file with CSV extension
            ("", False),  # Empty string
            ("data.", False),  # Trailing dot, no extension
            ("data.csvv", False),  # Almost CSV
            ("data.cs", False),  # Incomplete extension
        ],
    )
    def test_validates_file_extensions(self, filename, expected):
        """Various filenames → correct validation result"""
        result = allowed_file(filename)
        assert result == expected, f"Failed for filename: {filename}"

    def test_handles_path_with_directories(self):
        """Full path with directories → validates extension"""
        assert allowed_file("/path/to/file.csv") is True
        assert allowed_file("/path/to/file.txt") is False
        assert allowed_file("../data/dataset.csv") is True


class TestDropColumns:
    """Test column removal from DataFrame"""

    def test_drops_single_column(self):
        """Drop one column → returns True, modifies DataFrame in place"""
        df = pd.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6], "col3": [7, 8, 9]})

        result = drop_columns(df, ["col2"])

        assert result is True
        assert "col2" not in df.columns
        assert "col1" in df.columns
        assert "col3" in df.columns
        assert len(df.columns) == 2

    def test_drops_multiple_columns(self):
        """Drop multiple columns → all removed"""
        df = pd.DataFrame(
            {"col1": [1, 2, 3], "col2": [4, 5, 6], "col3": [7, 8, 9], "col4": [10, 11, 12]}
        )

        result = drop_columns(df, ["col2", "col4"])

        assert result is True
        assert "col2" not in df.columns
        assert "col4" not in df.columns
        assert "col1" in df.columns
        assert "col3" in df.columns
        assert len(df.columns) == 2

    def test_handles_non_existent_columns(self):
        """Drop non-existent column → handles gracefully with errors='ignore'"""
        df = pd.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6]})

        # Should handle gracefully (errors='ignore')
        result = drop_columns(df, ["col1", "non_existent"])

        assert result is True
        assert "col1" not in df.columns
        assert "col2" in df.columns

    def test_drops_all_columns_except_one(self):
        """Drop all but one → single column remains"""
        df = pd.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6], "col3": [7, 8, 9]})

        result = drop_columns(df, ["col1", "col2"])

        assert result is True
        assert len(df.columns) == 1
        assert "col3" in df.columns


class TestCalculateMissingPercentages:
    """Test missing value percentage calculations"""

    def test_calculates_no_missing_values(self):
        """No missing values → 0% for all columns"""
        df = pd.DataFrame({"col1": [1, 2, 3, 4, 5], "col2": ["a", "b", "c", "d", "e"]})

        result = calculate_missing_percentages(df)

        assert result["col1"] == 0.0
        assert result["col2"] == 0.0

    def test_calculates_partial_missing_values(self):
        """Some missing values → correct percentage"""
        df = pd.DataFrame(
            {
                "col1": [1, 2, np.nan, 4, np.nan],  # 2/5 = 40%
                "col2": ["a", None, "c", "d", "e"],  # 1/5 = 20%
            }
        )

        result = calculate_missing_percentages(df)

        assert result["col1"] == pytest.approx(40.0, rel=1e-2)
        assert result["col2"] == pytest.approx(20.0, rel=1e-2)

    def test_calculates_all_missing_values(self):
        """All missing values → 100%"""
        df = pd.DataFrame({"col1": [np.nan, np.nan, np.nan], "col2": [None, None, None]})

        result = calculate_missing_percentages(df)

        assert result["col1"] == 100.0
        assert result["col2"] == 100.0

    def test_handles_empty_dataframe(self):
        """Empty DataFrame → returns empty dict or handles gracefully"""
        df = pd.DataFrame()

        result = calculate_missing_percentages(df)

        assert isinstance(result, dict)
        assert len(result) == 0

    def test_handles_single_row(self):
        """Single row → correct percentage"""
        df = pd.DataFrame({"col1": [1], "col2": [np.nan]})

        result = calculate_missing_percentages(df)

        assert result["col1"] == 0.0
        assert result["col2"] == 100.0

    def test_mixed_data_types_with_missing(self):
        """Mixed dtypes with missing → correct calculation"""
        df = pd.DataFrame(
            {
                "int_col": [1, 2, np.nan, 4],
                "str_col": ["a", "b", None, "d"],
                "float_col": [1.1, np.nan, 3.3, np.nan],
            }
        )

        result = calculate_missing_percentages(df)

        assert result["int_col"] == 25.0
        assert result["str_col"] == 25.0
        assert result["float_col"] == 50.0


class TestIdentifyQuasiIdentifiersWithDistinctValues:
    """Test quasi-identifier detection"""

    def test_identifies_high_cardinality_columns(self):
        """Columns with many distinct values → returns distinct values and mappings"""
        df = pd.DataFrame(
            {
                "id": range(100),  # 100 distinct - high cardinality
                "name": [f"Person{i}" for i in range(100)],  # 100 distinct
                "age": [20, 25, 30, 35, 40] * 20,  # 5 distinct - low cardinality
            }
        )

        # Function requires quasi_identifiers parameter
        quasi_identifiers = ["id", "name"]
        distinct_values, mappings = identify_quasi_identifiers_with_distinct_values(
            df, quasi_identifiers
        )

        assert "id" in distinct_values
        assert "name" in distinct_values
        assert len(distinct_values["id"]) == 100
        assert len(distinct_values["name"]) == 100

        # Check mappings are initialized as empty dicts
        assert "id" in mappings
        assert "name" in mappings
        assert mappings["id"] == {}
        assert mappings["name"] == {}

    def test_excludes_columns_not_in_quasi_identifiers(self):
        """Columns not specified → not included in results"""
        df = pd.DataFrame(
            {"id": range(50), "gender": ["M", "F"] * 25, "age": [20, 25, 30, 35, 40] * 10}
        )

        # Only specify 'id' as quasi-identifier
        quasi_identifiers = ["id"]
        distinct_values, mappings = identify_quasi_identifiers_with_distinct_values(
            df, quasi_identifiers
        )

        assert "id" in distinct_values
        assert "gender" not in distinct_values
        assert "age" not in distinct_values

    def test_handles_empty_quasi_identifiers_list(self):
        """Empty quasi-identifiers list → empty results"""
        df = pd.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6]})

        distinct_values, mappings = identify_quasi_identifiers_with_distinct_values(df, [])

        assert len(distinct_values) == 0
        assert len(mappings) == 0

    def test_returns_distinct_values_as_strings(self):
        """All values converted to strings in distinct values"""
        df = pd.DataFrame({"numeric_col": [1, 2, 3, 4, 5], "mixed_col": [1, "two", 3.0, "four", 5]})

        quasi_identifiers = ["numeric_col", "mixed_col"]
        distinct_values, mappings = identify_quasi_identifiers_with_distinct_values(
            df, quasi_identifiers
        )

        # Values should be strings
        assert all(isinstance(v, str) for v in distinct_values["numeric_col"])
        assert all(isinstance(v, str) for v in distinct_values["mixed_col"])


class TestMapValuesAndOutputPercentages:
    """Test value mapping and percentage calculations"""

    def test_applies_mappings_and_calculates_percentages(self):
        """Applies mappings to columns → returns modified df and percentages"""
        df = pd.DataFrame(
            {
                "age": ["25", "30", "25", "35", "30", "25"],
                "city": ["NYC", "LA", "NYC", "SF", "LA", "NYC"],
            }
        )

        # Define mappings: group ages into ranges
        mappings = {
            "age": {"25": "20-30", "30": "20-30", "35": "30-40"},
            "city": {},  # No mapping for city
        }

        columns = ["age", "city"]
        modified_df, result = map_values_and_output_percentages(df, columns, mappings)

        # Check that DataFrame was modified
        assert modified_df["age"].tolist() == ["20-30", "20-30", "20-30", "30-40", "20-30", "20-30"]

        # Check percentages
        assert isinstance(result, dict)
        assert "age" in result
        # 5/6 = 83.33% for '20-30', 1/6 = 16.67% for '30-40'
        assert result["age"]["20-30"] == pytest.approx(83.33, abs=0.5)
        assert result["age"]["30-40"] == pytest.approx(16.67, abs=0.5)

    def test_handles_columns_without_mappings(self):
        """Columns with empty mappings → unchanged, percentages calculated"""
        df = pd.DataFrame({"category": ["A", "A", "B", "B", "B", "C"]})

        mappings = {"category": {}}  # Empty mapping
        columns = ["category"]
        modified_df, result = map_values_and_output_percentages(df, columns, mappings)

        # Values should be unchanged
        assert modified_df["category"].tolist() == ["A", "A", "B", "B", "B", "C"]

        # Percentages calculated
        assert result["category"]["A"] == pytest.approx(33.33, abs=0.5)
        assert result["category"]["B"] == pytest.approx(50.0, abs=0.5)
        assert result["category"]["C"] == pytest.approx(16.67, abs=0.5)

    def test_handles_column_not_in_dataframe(self):
        """Column not in DataFrame → skipped"""
        df = pd.DataFrame({"col1": ["A", "B", "C"]})

        mappings = {"col1": {"A": "X"}, "non_existent": {}}
        columns = ["col1", "non_existent"]
        modified_df, result = map_values_and_output_percentages(df, columns, mappings)

        # Should handle gracefully
        assert "col1" in result
        assert "non_existent" not in result

    def test_handles_numeric_values_converted_to_strings(self):
        """Numeric values → converted to strings for mapping"""
        df = pd.DataFrame({"numbers": [1, 1, 2, 2, 2, 3]})

        mappings = {"numbers": {"1": "low", "2": "medium", "3": "high"}}
        columns = ["numbers"]
        modified_df, result = map_values_and_output_percentages(df, columns, mappings)

        # Check values were mapped
        assert "low" in modified_df["numbers"].values
        assert "medium" in modified_df["numbers"].values
        assert "high" in modified_df["numbers"].values

        # Check percentages
        assert result["numbers"]["low"] == pytest.approx(33.33, abs=0.5)
        assert result["numbers"]["medium"] == pytest.approx(50.0, abs=0.5)
        assert result["numbers"]["high"] == pytest.approx(16.67, abs=0.5)


class TestDataHelpersIntegration:
    """Integration tests for combined workflows"""

    def test_complete_data_analysis_workflow(self):
        """Load data → calculate missing → identify quasi-identifiers → drop columns"""
        # Create test dataset
        df = pd.DataFrame(
            {
                "patient_id": [f"P{i}" for i in range(100)],  # Quasi-identifier
                "ssn": [f"SSN{i}" for i in range(100)],  # Quasi-identifier
                "age": np.random.randint(20, 80, 100),
                "gender": np.random.choice(["M", "F"], 100),
                "diagnosis": np.random.choice(["A", "B", "C"], 100),
                "value": np.random.randn(100),
            }
        )

        # Add some missing values
        df.loc[0:9, "age"] = np.nan
        df.loc[20:24, "value"] = np.nan

        # Step 1: Calculate missing percentages
        missing_pct = calculate_missing_percentages(df)
        assert missing_pct["age"] == 10.0
        assert missing_pct["value"] == 5.0

        # Step 2: Identify quasi-identifiers
        quasi_identifier_cols = ["patient_id", "ssn"]
        distinct_vals, mappings = identify_quasi_identifiers_with_distinct_values(
            df, quasi_identifier_cols
        )
        assert "patient_id" in distinct_vals
        assert "ssn" in distinct_vals

        # Step 3: Drop quasi-identifiers
        result = drop_columns(df, ["patient_id", "ssn"])
        assert result is True
        assert "patient_id" not in df.columns
        assert "ssn" not in df.columns

        # Step 4: Analyze remaining data with mappings
        gender_mappings = {"gender": {}}  # No mapping, just get distribution
        df_mapped, gender_dist = map_values_and_output_percentages(df, ["gender"], gender_mappings)
        assert "M" in gender_dist["gender"]
        assert "F" in gender_dist["gender"]
        total = gender_dist["gender"]["M"] + gender_dist["gender"]["F"]
        assert total == pytest.approx(100.0, abs=0.1)

    def test_file_validation_before_processing(self):
        """Validate file → process only valid files"""
        valid_files = ["data.csv", "dataset.CSV", "file.backup.csv"]
        invalid_files = ["data.txt", "data.xlsx", "data"]

        for filename in valid_files:
            assert allowed_file(filename) is True

        for filename in invalid_files:
            assert allowed_file(filename) is False
