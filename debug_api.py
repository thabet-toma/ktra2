import requests
import json

BASE_URL = 'http://localhost:8000'

def test_endpoint(name, url):
    print(f"--- Testing {name} ---")
    print(f"URL: {url}")
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    print(f"Success! Received list with {len(data)} items.")
                    if len(data) > 0:
                        print(f"Sample item keys: {list(data[0].keys())}")
                elif isinstance(data, dict):
                    print(f"Success! Received dict. Keys: {list(data.keys())}")
                    if 'results' in data:
                        print(f"It seems paginated. Results count: {len(data['results'])}")
                else:
                    print("Received unknown data structure.")
            except json.JSONDecodeError:
                print("Error: Could not decode JSON.")
                print(f"Raw content: {response.text[:200]}...")
        else:
            print(f"Request Failed.")
            print(f"Response: {response.text[:200]}")
    except Exception as e:
        print(f"EXCEPTION: {str(e)}")
    print("\n")

if __name__ == "__main__":
    print("Starting API Debug...\n")
    
    # Test 1: Partners
    test_endpoint("Partners", f"{BASE_URL}/api/partners/")
    
    # Test 2: Cost Centers
    test_endpoint("Cost Centers", f"{BASE_URL}/api/accounting/cost-centers/")
    
    # Test 3: Cheques
    test_endpoint("Cheques", f"{BASE_URL}/api/accounting/cheques/")
    
    # Test 4: Accounts
    test_endpoint("Accounts", f"{BASE_URL}/api/accounting/accounts/")
