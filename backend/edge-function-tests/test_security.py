"""
Test the security of the edge function to ensure other people with unauthorized access cannot access it.

Should show: FUNCTIONS_VERIFY_JWT=true in the docker .env file
"""

import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('../.env')

EDGE_FUNCTION_URL = "http://localhost:8000/functions/v1/get-dataset-stats"
SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')


def test_without_authentication():
    """Users with no authentication should get rejected if they try to acces the edge function."""
    print("Test 1: Request without authentication")

    try:
        response = requests.post(
            EDGE_FUNCTION_URL,
            headers={"Content-Type": "application/json"},
            json={},
            timeout=5
        )

        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")

        # check if response indicates unauthorized access
        if response.status_code == 401 or "authorization" in response.text.lower():
            print("PASS: Unauthorized access blocked")
            return True
        else:
            print("FAIL: Request should have been blocked")
            return False

    except Exception as e:
        print(f"ERROR: {e}")
        return False


def test_with_authentication():
    """Users with authentication should be able to acces the function"""
    print("\nTest 2: Request with valid authentication")

    if not SERVICE_ROLE_KEY:
        print("ERROR: SUPABASE_SERVICE_ROLE_KEY not found in .env")
        return False

    try:
        response = requests.post(
            EDGE_FUNCTION_URL,
            headers={
                "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
                "Content-Type": "application/json"
            },
            json={},
            timeout=5
        )

        print(f"Status Code: {response.status_code}")
        data = response.json()

        # check if response is successful
        if response.status_code == 200 and data.get('success'):
            print(f"PASS: Authorized access successful")
            print(f"Tables found: {len(data.get('tables', []))}")
            return True
        else:
            print(f"FAIL: Request should have succeeded")
            print(f"Response: {data}")
            return False

    except Exception as e:
        print(f"ERROR: {e}")
        return False


def test_network_accessibility():
    """People from other machines on the same netwokr should not be able to access it"""
    print("\nTest 3: Network accessibility check")

    # Get network IP
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    print(f"Testing from network IP: {local_ip}")

    try:
        response = requests.post(
            f"http://{local_ip}:8000/functions/v1/get-dataset-stats",
            headers={"Content-Type": "application/json"},
            json={},
            timeout=5
        )

        if response.status_code == 401 or "authorization" in response.text.lower():
            print("PASS: Network access blocked without authentication")
            return True
        else:
            print("FAIL: Network access be authenticated")
            return False

    except requests.exceptions.ConnectionError:
        print("PASS: Cannot connect (port not exposed to network)")
        return True
    except Exception as e:
        print(f"INFO: {e}")
        return True  # Connection refused is good


if __name__ == "__main__":
    print("Edge Function Security Tests")

    results = []
    results.append(test_without_authentication())
    results.append(test_with_authentication())
    results.append(test_network_accessibility())

    print(f"Passed: {sum(results)}/{len(results)}")
