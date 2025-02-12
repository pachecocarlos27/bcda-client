
import os
import time
import requests
import json
import base64
import pandas as pd
from .config import BCDAConfig
from .utils import get_default_since_date, flatten_dict, print_data_summary

class BCDAClient:
    def __init__(self, client_id, client_secret, base_url=None, is_sandbox=True, debug=False):
        self.config = BCDAConfig(client_id, client_secret, base_url, is_sandbox)
        self.access_token = None
        self.debug = debug
        
    def authenticate(self):
        auth_string = base64.b64encode(
            f"{self.config.client_id}:{self.config.client_secret}".encode()
        ).decode()
        
        headers = {
            "Authorization": f"Basic {auth_string}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "client_credentials",
            "scope": "system/*.read"
        }

        response = requests.post(self.config.auth_endpoint, data=data, headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Authentication failed. Status: {response.status_code}, Response: {response.text}")

        self.access_token = response.json()["access_token"]
        return self.access_token

    def _initiate_export_job(self, endpoint_name, endpoint_url, incremental=False):
        if not self.access_token:
            self.authenticate()
            
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/fhir+json",
            "Prefer": "respond-async"
        }
        
        params = {"_outputFormat": "application/fhir+ndjson"}
        
        if endpoint_name in self.config.resource_types:
            params["_type"] = self.config.resource_types[endpoint_name]
            
        if incremental:
            params["_since"] = get_default_since_date()
        
        if endpoint_name in ["Metadata", "Jobs", "Attribution_Status"]:
            response = requests.get(endpoint_url, headers=headers)
            if response.status_code == 200:
                return {"output": [{
                    "type": endpoint_name,
                    "url": endpoint_url,
                    "response": response.json()
                }]}
            else:
                raise Exception(f"Failed to get {endpoint_name}. Status: {response.status_code}, Response: {response.text}")
        
        try:
            response = requests.get(endpoint_url, headers=headers, params=params)
            
            if response.status_code == 400:
                error_msg = response.json().get('error', response.text)
                print(f"Error response for {endpoint_name}: {error_msg}")
                raise Exception(f"Failed to initiate export job. Status: {response.status_code}, Response: {response.text}")
            
            if response.status_code != 202:
                raise Exception(f"Failed to initiate export job. Status: {response.status_code}, Response: {response.text}")

            job_url = response.headers.get("Content-Location")
            if not job_url:
                raise Exception("Content-Location header is missing in the response")
            
            return job_url
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error occurred: {str(e)}")

    def _poll_job(self, job_url):
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/fhir+json"
        }

        while True:
            response = requests.get(job_url, headers=headers)
            
            if response.status_code == 202:
                time.sleep(self.config.poll_interval)
                continue

            if response.status_code == 200:
                job_status = response.json()
                
                if "error" in job_status and job_status["error"]:
                    raise Exception(f"Job completed with errors: {job_status['error']}")

                return job_status

            raise Exception(f"Unexpected status code: {response.status_code}")

    def download_data(self, output_dir=None, include_csv=False, incremental=False):
        if not output_dir:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            extract_type = "incremental" if incremental else "full"
            output_dir = f"bcda_export_{extract_type}_{timestamp}"
            
        os.makedirs(output_dir, exist_ok=True)
        
        if not self.access_token:
            self.authenticate()

        results = {}
        for endpoint_name, endpoint_url in self.config.export_endpoints.items():
            try:
                if endpoint_name in ["Metadata", "Jobs", "Attribution_Status"]:
                    job_status = self._initiate_export_job(endpoint_name, endpoint_url, incremental)
                    output_files = job_status["output"]
                else:
                    job_url = self._initiate_export_job(endpoint_name, endpoint_url, incremental)
                    job_status = self._poll_job(job_url)
                    output_files = job_status.get("output", [])

                if output_files:
                    results[endpoint_name] = self._save_files(
                        output_files, 
                        output_dir, 
                        include_csv
                    )

            except Exception as e:
                print(f"Error processing {endpoint_name}: {str(e)}")
                continue

        print_data_summary(output_dir)
        return results

    def _save_files(self, output_files, base_dir, include_csv):
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        parquet_dir = os.path.join(base_dir, "parquet")
        os.makedirs(parquet_dir, exist_ok=True)
        
        if include_csv:
            csv_dir = os.path.join(base_dir, "csv")
            os.makedirs(csv_dir, exist_ok=True)

        # Use a single timestamp for all files in this batch
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        # Track processed resource types to avoid duplicates
        processed_resources = set()
        saved_files = []

        for file_info in output_files:
            resource_type = file_info["type"]
            
            # Skip if we've already processed this resource type
            if resource_type in processed_resources:
                print(f"Skipping duplicate resource type: {resource_type}")
                continue
            
            processed_resources.add(resource_type)
            file_url = file_info["url"]

            safe_resource_type = "".join(c for c in resource_type if c.isalnum() or c in ('-', '_'))
            parquet_filename = f"{safe_resource_type}_{timestamp}.parquet"
            parquet_filepath = os.path.join(parquet_dir, parquet_filename)

            print(f"\nDownloading {resource_type} data from: {file_url}")
            response = requests.get(file_url, headers=headers)
            
            if response.status_code != 200:
                print(f"Failed to download file for {resource_type}. Status: {response.status_code}")
                continue

            try:
                data = [json.loads(line) for line in response.text.strip().split('\n') if line]
                
                if not data:  # Skip empty responses
                    print(f"No data found for {resource_type}")
                    continue
                
                df = pd.DataFrame(data)
                df.to_parquet(parquet_filepath, index=False)
                saved_files.append(parquet_filepath)
                print(f"Saved {resource_type} data to {parquet_filepath}")
                print(f"Number of records: {len(df)}")
                
                if include_csv:
                    csv_filename = parquet_filename.replace('.parquet', '.csv')
                    csv_filepath = os.path.join(csv_dir, csv_filename)
                    
                    flattened_data = [flatten_dict(d) for d in data]
                    df_flat = pd.DataFrame(flattened_data)
                    
                    for col in df_flat.columns:
                        df_flat[col] = df_flat[col].apply(
                            lambda x: str(x) if isinstance(x, (dict, list)) else x
                        )
                    
                    df_flat = df_flat.reindex(sorted(df_flat.columns), axis=1)
                    df_flat.to_csv(csv_filepath, index=False)
                    saved_files.append(csv_filepath)
                    print(f"Saved flattened {resource_type} data to {csv_filepath}")
                    print(f"Number of columns in CSV: {len(df_flat.columns)}")
                
            except Exception as e:
                print(f"Error processing {resource_type} data: {str(e)}")
                continue

        return saved_files 