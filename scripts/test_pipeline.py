import os
import requests
import time
import glob
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

API_URL = "http://localhost:6000/api/v1"
DATASET_PATH = "/Users/abhiram/Downloads/Even/lbmaske"

def upload_file(file_path):
    try:
        with open(file_path, "rb") as f:
            files = {"files": (os.path.basename(file_path), f, "image/png")}
            response = requests.post(f"{API_URL}/upload", files=files)
            if response.status_code == 200:
                return response.json()[0]
            else:
                print(f"Failed to upload {file_path}: {response.text}")
                return None
    except Exception as e:
        print(f"Error uploading {file_path}: {e}")
        return None

def save_result(document_id, data):
    output_dir = "test_results"
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{document_id}.json")
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

def check_status(document_id):
    try:
        response = requests.get(f"{API_URL}/results/{document_id}")
        if response.status_code == 200:
            data = response.json()
            doc_status = data['document']['status']
            
            if doc_status == 'completed':
                extraction = data.get('extraction', {})
                if extraction:
                    save_result(document_id, extraction.get('extracted_data'))
            
            return doc_status
        return "unknown"
    except Exception:
        return "error"


def run_test(num_files=10):
    print(f"Starting test with {num_files} files from {DATASET_PATH}...")
    
    # Get all png files
    all_files = glob.glob(os.path.join(DATASET_PATH, "*.png"))
    test_files = all_files[:num_files]
    
    if not test_files:
        print("No PNG files found in dataset path.")
        return

    print(f"Found {len(all_files)} files. Testing with {len(test_files)} files.")

    # Upload
    uploaded_docs = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(upload_file, test_files)
        uploaded_docs = [r for r in results if r]

    print(f"Successfully uploaded {len(uploaded_docs)} files.")
    
    if not uploaded_docs:
        return

    # Monitor
    print("Monitoring processing status...")
    start_time = time.time()
    
    while True:
        completed = 0
        failed = 0
        pending = 0
        
        for doc in uploaded_docs:
            status = check_status(doc['id'])
            if status == 'completed':
                completed += 1
            elif status == 'failed':
                failed += 1
            else:
                pending += 1
        
        print(f"Status: {completed} Completed, {failed} Failed, {pending} Pending")
        
        if pending == 0:
            break
            
        if time.time() - start_time > 300: # 5 min timeout
            print("Timeout reached.")
            break
            
        time.sleep(2)

    duration = time.time() - start_time
    print(f"\nTest Finished in {duration:.2f} seconds.")
    print(f"Final Results: {completed}/{len(uploaded_docs)} successful.")
    if completed > 0:
        print(f"Extracted JSON results are saved in: {os.path.abspath('test_results')}")

if __name__ == "__main__":
    import sys
    count = 10
    if len(sys.argv) > 1:
        count = int(sys.argv[1])
    run_test(count)
