import requests
import json
import time

# API Gateway endpoint URL
api_url = "https://z5sgimr3pb.execute-api.us-east-1.amazonaws.com/"

# Test the /initiate endpoint
def test_initiate():
    initiate_url = f"{api_url}/initiate/research"
    payload = {
        "question": "latest news on ticker BMY"
    }
    start_time = time.time()  # Start measuring time
    response = requests.post(initiate_url, json=payload)
    end_time = time.time()  # Stop measuring time
    if response.status_code == 200:
        process_id = response.json()["processId"]
        print(f"Initiate test passed. Process ID: {process_id}")
        print(f"Total time to complete request: {end_time - start_time} seconds")  # Print total time
        return process_id
    else:
        print(f"Initiate test failed. Status code: {response.status_code}")
        return None

# Test the /status/{processId} endpoint
def test_status(process_id):
    status_url = f"{api_url}/status/{process_id}"
    loop_start_time = time.time()  # Start measuring time for the while loop
    while True:
        response = requests.get(status_url)
        if response.status_code == 200:
            result = response.json()
            status = result["status"]
            if status == "COMPLETED":
                print(f"Status test passed. Result: {result['result']}")
                break
            elif status == "FAILED":
                print("Status test failed. Process failed.")
                break
            else:
                print(f"Process status: {status}. Waiting...")
                time.sleep(5)  # Wait for 5 seconds before polling again
        else:
            print(f"Status test failed. Status code: {response.status_code}")
            break
    loop_end_time = time.time()  # Stop measuring time for the while loop
    print(f"Total time spent in the while loop: {loop_end_time - loop_start_time} seconds")  # Print total time

# Run the tests
process_id = test_initiate()
if process_id:
    test_status(process_id)