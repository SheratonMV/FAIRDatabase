"""
This file should test the output of the edge function.

The output should only print the samples, the distance matrix and the coordinates. The actual actual abundance data is not sent for security reasons

A hardcoded dataset is used for testing purposes, but it can be replaced with any other dataset.
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

def test_edge_function_output():
    url = "http://localhost:8000/functions/v1/get-dataset-visualization"

    payload = {
        "table_name": "test_edge_function_dataset2_1767949660_p1",
        "row_limit": 10,
        "column_limit": 10,
        "metric": "bray_curtis"
    }

    response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
    data = response.json()

    print(data)

if __name__ == "__main__":
    test_edge_function_output()
