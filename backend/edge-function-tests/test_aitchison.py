"""
This file should test whether the resulted output from the edge function is actually valid with a dummy dataset for testing purposes.

In this case a hardcoded dataset is used but it can be replaced with any other dataset for testing.
"""

import requests
import os
from dotenv import load_dotenv

load_dotenv('../.env')

SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
HEADERS = {
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "Content-Type": "application/json"
}

def test_aitchison_transformation():
    url = "http://localhost:8000/functions/v1/get-dataset-visualization"

    payload = {
        "table_name": "test_edge_function_dataset2_1767949660_p1",
        "row_limit": 10,
        "column_limit": 10,
        "metric": "aitchison"
    }

    response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
    data = response.json()
    print("Response Data:", data)
    matrix = data['data']['distance_matrix']

    # Test if the matrix is symmetric
    symmetric = all(
        abs(matrix[i][j] - matrix[j][i]) < 0.0001
        for i in range(len(matrix))
        for j in range(len(matrix))
    )
    print(f"Symmetry: {symmetric}")

    # In a matrix the diagonal should be zero
    diagonal_zero = all(matrix[i][i] == 0 for i in range(len(matrix)))
    print(f"Diagonal is zero: {diagonal_zero}")

    # In a matrix all values should be above or equal to zero
    non_negative = all(matrix[i][j] >= 0 for i in range(len(matrix)) for j in range(len(matrix)))
    print(f"Non-negative: {non_negative}")

    print(f"\nAll tests passed: {symmetric and diagonal_zero and non_negative}")

if __name__ == "__main__":
    test_aitchison_transformation()
