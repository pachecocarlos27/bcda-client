import os
import time
import requests
import json
import base64
import pandas as pd
from .config import BCDAConfig
from .utils import get_default_since_date, flatten_dict, print_data_summary
from datetime import datetime, timedelta, timezone
import pyarrow as pa
import pyarrow.parquet as pq
from typing import List, Dict, Optional
import logging
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

class BCDAClient:
    def __init__(self, client_id, client_secret, base_url=None, is_sandbox=True, debug=False):
        self.config = BCDAConfig(client_id, client_secret, base_url, is_sandbox)
        self.access_token = None
        self.token_expiry = None
        self.debug = debug
        self.environment = "sandbox" if is_sandbox else "production"
        
        # Add logger initialization
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            level=logging.DEBUG if debug else logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Add a Session for reusing connections (performance improvement)
        self.session = requests.Session()

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

        response = self.session.post(self.config.auth_endpoint, data=data, headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Authentication failed. Status: {response.status_code}, Response: {response.text}")

        token_data = response.json()
        self.access_token = token_data["access_token"]
        # Set token_expiry - use 'expires_in' if provided; default to 20 minutes otherwise
        if "expires_in" in token_data:
            expires_in_str = token_data["expires_in"]
            # Convert expires_in to an integer in case it's returned as a string
            expires_in_seconds = int(expires_in_str)
            self.token_expiry = datetime.now().timestamp() + expires_in_seconds
        else:
            # Default to 20 minutes if unsupported or missing
            self.token_expiry = datetime.now().timestamp() + (20 * 60)
        
        return self.access_token

    def _get_headers(self, endpoint_name, is_bulk=False):
        """Get appropriate headers for each endpoint"""
        base_headers = {"Authorization": f"Bearer {self.access_token}"}
        
        if endpoint_name in self.config.endpoint_headers:
            headers = self.config.endpoint_headers[endpoint_name].copy()
        elif is_bulk:
            headers = self.config.endpoint_headers["bulk"].copy()
        else:
            headers = self.config.endpoint_headers["default"].copy()
            
        headers.update(base_headers)
        return headers

    def _initiate_export_job(self, endpoint_name, endpoint_url, incremental=False, since_date=None):
        if not self.access_token:
            self.authenticate()
            
        # For bulk export endpoints
        headers = self._get_headers(endpoint_name, is_bulk=True)
        params = {"_outputFormat": "application/fhir+ndjson"}
        
        # Get endpoint-specific parameters
        if hasattr(self.config, 'endpoint_params') and endpoint_name in self.config.endpoint_params:
            params.update(self.config.endpoint_params[endpoint_name])
        
        # Get resource types from endpoint_resource_types if available
        resource_types = self.config.endpoint_resource_types.get(endpoint_name)
        if resource_types and isinstance(resource_types, list):
            params["_type"] = ",".join(resource_types)
        
        if incremental and since_date:
            params["_since"] = since_date
        
        try:
            print(f"Initiating bulk export job for {endpoint_name}...")
            
            if self.debug:
                print(f"Request URL: {endpoint_url}")
                print(f"Request Headers: {headers}")
                print(f"Request Params: {params}")
            
            response = requests.get(endpoint_url, headers=headers, params=params, timeout=30)
            
            if self.debug:
                print(f"Response Status: {response.status_code}")
                print(f"Response Headers: {dict(response.headers)}")
                if response.status_code != 202:
                    print(f"Response Body: {response.text}")
            
            if response.status_code == 202:
                job_url = response.headers.get("Content-Location")
                if not job_url:
                    raise Exception("Content-Location header is missing in the response")
                
                if self.debug:
                    print(f"Job URL for {endpoint_name}: {job_url}")
                
                return job_url
            else:
                error_msg = response.json() if response.text else {"error": "No response body"}
                print(f"Error response for {endpoint_name}: {json.dumps(error_msg, indent=2)}")
                raise Exception(f"Failed to initiate export job. Status: {response.status_code}, Response: {response.text}")
            
        except requests.exceptions.Timeout:
            raise Exception(f"Timeout while initiating export job for {endpoint_name}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error occurred: {str(e)}")

    def _poll_job(self, job_url):
        """Poll job status and get output files"""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/fhir+json"
        }

        max_attempts = 5
        attempt = 0
        backoff_time = 60  # Start with 1 minute
        
        while attempt < max_attempts:
            try:
                if self.debug:
                    print(f"\nPolling job at: {job_url}")
                    print(f"Headers: {headers}")
                
                response = requests.get(job_url, headers=headers, timeout=30)
                
                if self.debug:
                    print(f"Poll response status: {response.status_code}")
                    print(f"Poll response headers: {dict(response.headers)}")
                    print(f"Poll response body: {response.text[:500]}...")
                
                if response.status_code == 401:
                    print("Access token expired, refreshing...")
                    self.authenticate()
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    continue
                
                if response.status_code == 202:
                    attempt += 1
                    remaining = max_attempts - attempt
                    elapsed_minutes = (attempt * backoff_time) // 60
                    
                    print(f"\rWaiting for job completion... (attempt: {attempt}/5, elapsed: {elapsed_minutes}m, next check in: {backoff_time//60}m)", end="")
                    time.sleep(backoff_time)
                    backoff_time = min(300, backoff_time * 2)
                    continue

                if response.status_code == 200:
                    print("\nJob completed successfully!")
                    result = response.json()
                    if self.debug:
                        print(f"Job result: {json.dumps(result, indent=2)}")
                    return result

                raise Exception(f"Unexpected status code: {response.status_code}")

            except Exception as e:
                print(f"\nError during polling: {str(e)}")
                attempt += 1
                if attempt < max_attempts:
                    time.sleep(backoff_time)
            
        raise Exception(f"Job polling timed out after {max_attempts} attempts")

    def download_data(self, output_dir=None, include_csv=False, incremental=False):
        if incremental:
            # Break down incremental load into smaller date ranges
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=30)  # Adjust window size as needed
            date_ranges = []
            
            while start_date < end_date:
                date_ranges.append(start_date.isoformat() + 'Z')
                start_date += timedelta(days=7)  # Process 7 days at a time
            
            all_results = {}
            for since_date in date_ranges:
                print(f"\nProcessing data since {since_date}")
                results = self._process_endpoints(output_dir, include_csv, True, since_date)
                self._merge_results(all_results, results)
            
            return all_results
        else:
            return self._process_endpoints(output_dir, include_csv, False)

    def _process_endpoints(self, output_dir=None, include_csv=False, incremental=False, since_date=None):
        if not output_dir:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            extract_type = "incremental" if incremental else "full"
            output_dir = f"bcda_export_{extract_type}_{timestamp}"
            
        os.makedirs(output_dir, exist_ok=True)
        
        if not self.access_token:
            self.authenticate()

        results = {}
        
        # Group endpoints by type for optimal processing
        bulk_endpoints = []
        direct_endpoints = []
        
        for name, url in self.config.export_endpoints.items():
            if name in ["Metadata", "Jobs", "Attribution_Status"]:
                direct_endpoints.append((name, url))
            else:
                bulk_endpoints.append((name, url))

        # Process Claims data through Group endpoint
        if "Group_Claims" in self.config.export_endpoints:
            try:
                print("\nProcessing Claims data...")
                claims_url = self.config.export_endpoints["Group_Claims"]
                
                # Add a default since date for claims if not provided
                claims_since_date = since_date or "2020-12-01T00:00:00.000-05:00"
                
                claims_result = self._try_all_resource_types(
                    "Group_Claims", 
                    claims_url, 
                    output_dir, 
                    include_csv, 
                    True,  # Always use incremental for claims
                    claims_since_date
                )
                if claims_result:
                    results["Claims"] = claims_result
            except Exception as e:
                print(f"Error processing Claims data: {str(e)}")

        # Process direct endpoints first (these are quick)
        if direct_endpoints:  # Only create executor if we have endpoints to process
            with ThreadPoolExecutor(max_workers=max(1, len(direct_endpoints))) as executor:
                future_to_endpoint = {
                    executor.submit(
                        self._process_single_endpoint, 
                        name, url, output_dir, include_csv, incremental, since_date
                    ): name 
                    for name, url in direct_endpoints
                }
                
                for future in as_completed(future_to_endpoint):
                    name = future_to_endpoint[future]
                    try:
                        result = future.result()
                        if result:
                            results[name] = result
                    except Exception as e:
                        print(f"Error processing {name}: {str(e)}")

        # Process bulk endpoints with improved concurrency
        max_concurrent_jobs = min(3, len(bulk_endpoints))  # Use at most 3 concurrent jobs
        if bulk_endpoints:  # Only process if we have bulk endpoints
            for i in range(0, len(bulk_endpoints), max_concurrent_jobs):
                batch = bulk_endpoints[i:i + max_concurrent_jobs]
                
                # Start all jobs in this batch
                active_jobs = []
                for name, url in batch:
                    try:
                        print(f"\nInitiating export for {name}...")
                        job_url = self._initiate_export_job(name, url, incremental, since_date)
                        active_jobs.append((name, job_url))
                    except Exception as e:
                        print(f"Failed to initiate {name}: {str(e)}")

                # Poll and process jobs as they complete
                if active_jobs:  # Only create executor if we have active jobs
                    with ThreadPoolExecutor(max_workers=max(1, len(active_jobs))) as executor:
                        future_to_job = {
                            executor.submit(self._poll_and_process_job, name, job_url, output_dir, include_csv): name
                            for name, job_url in active_jobs
                        }
                        
                        for future in as_completed(future_to_job):
                            name = future_to_job[future]
                            try:
                                result = future.result()
                                if result:
                                    results[name] = result
                            except Exception as e:
                                print(f"Error processing {name}: {str(e)}")

        print_data_summary(output_dir)
        return results

    def _try_all_resource_types(self, endpoint_name, endpoint_url, output_dir, include_csv, incremental=False, since_date=None):
        """Try all possible resource types for an endpoint"""
        successful_results = []
        
        # Special handling for Claims endpoint
        if endpoint_name == "Claims":
            try:
                print(f"\nProcessing Claims endpoint without resource type specification...")
                
                # Set up parameters for Claims
                params = {"_outputFormat": "application/fhir+ndjson"}
                if incremental:
                    params["_since"] = since_date or get_default_since_date()
                
                # Get Claims-specific headers
                headers = self._get_headers("Claims", is_bulk=True)
                
                if self.debug:
                    print(f"Claims Request URL: {endpoint_url}")
                    print(f"Claims Headers: {headers}")
                    print(f"Claims Params: {params}")
                
                response = requests.get(endpoint_url, headers=headers, params=params, timeout=30)
                
                if self.debug:
                    print(f"Claims Response Status: {response.status_code}")
                    print(f"Claims Response Headers: {dict(response.headers)}")
                    print(f"Claims Response Body: {response.text[:500]}...")
                
                if response.status_code == 202:
                    job_url = response.headers.get("Content-Location")
                    if job_url:
                        print(f"Got Claims job URL: {job_url}")
                        job_status = self._poll_job(job_url)
                        if job_status and job_status.get("output"):
                            saved_files = self._save_files(
                                job_status["output"], 
                                output_dir, 
                                include_csv,
                                resource_suffix="_Claims"
                            )
                            if saved_files:
                                successful_results.extend(saved_files)
                                print(f"Successfully saved Claims data")
                else:
                    print(f"Unexpected Claims response: {response.status_code}")
                    print(f"Response body: {response.text}")
                    
            except Exception as e:
                print(f"Error processing Claims endpoint: {str(e)}")
                
            return successful_results if successful_results else None
        
        # Handle other endpoints with resource type iteration
        resource_types = self.config.endpoint_resource_types.get(endpoint_name, self.config.resource_types_to_try)
        
        for resource_type in resource_types:
            try:
                print(f"\nTrying {endpoint_name} with resource type: {resource_type or 'None'}")
                
                # Set up parameters
                params = {"_outputFormat": "application/fhir+ndjson"}
                if resource_type:
                    params["_type"] = resource_type
                if incremental:
                    params["_since"] = since_date or get_default_since_date()
                
                # Try to initiate export
                headers = self._get_headers(endpoint_name, is_bulk=True)
                
                if self.debug:
                    print(f"Request URL: {endpoint_url}")
                    print(f"Request Headers: {headers}")
                    print(f"Request Params: {params}")
                
                response = requests.get(endpoint_url, headers=headers, params=params, timeout=30)
                
                if self.debug:
                    print(f"Response Status: {response.status_code}")
                    print(f"Response Headers: {dict(response.headers)}")
                
                if response.status_code == 202:
                    job_url = response.headers.get("Content-Location")
                    if not job_url:
                        continue
                        
                    try:
                        print(f"Got job URL: {job_url}")
                        # Poll and process the job
                        job_status = self._poll_job(job_url)
                        if job_status and job_status.get("output"):
                            # Save with resource type in filename
                            saved_files = self._save_files(
                                job_status["output"], 
                                output_dir, 
                                include_csv,
                                resource_suffix=f"_{resource_type}" if resource_type else ""
                            )
                            if saved_files:
                                successful_results.extend(saved_files)
                                print(f"Successfully saved files for {endpoint_name} with type {resource_type}")
                    except Exception as e:
                        print(f"Error processing job for {resource_type}: {str(e)}")
                        continue
                else:
                    print(f"Unexpected status code {response.status_code} for {endpoint_name} with type {resource_type}")
                    if self.debug:
                        print(f"Response body: {response.text}")
                        
            except Exception as e:
                print(f"Failed to try {resource_type}: {str(e)}")
                continue
            
        return successful_results if successful_results else None

    def _process_single_endpoint(self, endpoint_name, endpoint_url, output_dir, include_csv, incremental, since_date):
        """Process a single endpoint, trying all possible resource types for bulk endpoints"""
        try:
            if endpoint_name in ["Metadata", "Jobs", "Attribution_Status"]:
                # Handle direct endpoints normally
                job_status = self._initiate_export_job(endpoint_name, endpoint_url, incremental, since_date)
                output_files = job_status["output"]
                return self._save_files(output_files, output_dir, include_csv)
            else:
                # For bulk endpoints, try all resource types
                return self._try_all_resource_types(endpoint_name, endpoint_url, output_dir, include_csv, incremental, since_date)
            
        except Exception as e:
            print(f"Error processing {endpoint_name}: {str(e)}")
            return None

    def _merge_results(self, all_results, new_results):
        """Merge new results into all_results dictionary"""
        for endpoint, files in new_results.items():
            if endpoint not in all_results:
                all_results[endpoint] = []
            all_results[endpoint].extend(files)

    def _download_data_chunks(self, file_url, headers, resource_type):
        retries = 3
        while retries > 0:
            try:
                with requests.get(file_url, headers=headers, stream=True) as response:
                    if response.status_code == 401:
                        print("Access token expired, refreshing...")
                        self.authenticate()
                        headers["Authorization"] = f"Bearer {self.access_token}"
                        retries -= 1
                        continue
                        
                    if response.status_code != 200:
                        print(f"Failed to download file for {resource_type}. Status: {response.status_code}")
                        print(f"Response: {response.text}")
                        break

                    # Use line buffering for better streaming performance
                    buffer = []
                    buffer_size = 10000
                    
                    for line in response.iter_lines(decode_unicode=True, chunk_size=64*1024):  # 64KB chunks
                        if not line:
                            continue
                        
                        try:
                            record = json.loads(line)
                            buffer.append(record)
                            
                            if len(buffer) >= buffer_size:
                                yield buffer
                                buffer = []
                        except json.JSONDecodeError as e:
                            print(f"Error parsing JSON line for {resource_type}: {str(e)}")
                            continue

                    if buffer:
                        yield buffer

            except requests.exceptions.RequestException as e:
                print(f"Network error during download: {str(e)}")
                retries -= 1
                if retries > 0:
                    print(f"Retrying... {retries} attempts remaining")
                    time.sleep(5)
                continue
            break

    def _process_chunk(self, chunk, resource_type):
        """Process a single chunk of data"""
        try:
            return [flatten_dict(record) for record in chunk]
        except Exception as e:
            print(f"Error processing chunk for {resource_type}: {str(e)}")
            return []

    def _save_files(self, output_files, base_dir, include_csv, resource_suffix=""):
        """Save downloaded files with better error handling and debugging"""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        if self.debug:
            print(f"\nProcessing output files: {json.dumps(output_files, indent=2)}")
        
        parquet_dir = os.path.join(base_dir, "parquet")
        os.makedirs(parquet_dir, exist_ok=True)
        
        if include_csv:
            csv_dir = os.path.join(base_dir, "csv")
            os.makedirs(csv_dir, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        saved_files = []

        for file_info in output_files:
            try:
                if not isinstance(file_info, dict):
                    print(f"Skipping invalid file info: {file_info}")
                    continue
                
                resource_type = file_info.get("type")
                if not resource_type:
                    print(f"Missing resource type in file info: {file_info}")
                    continue
                
                if "response" in file_info:
                    # Handle direct endpoint responses
                    data = [file_info["response"]]
                else:
                    # Handle bulk export files
                    file_url = file_info.get("url")
                    if not file_url:
                        print(f"Missing URL in file info: {file_info}")
                        continue
                    
                    print(f"\nDownloading {resource_type} data from {file_url}")
                    data = []
                    for chunk in self._download_data_chunks(file_url, headers, resource_type):
                        data.extend(chunk)
                
                if not data:
                    print(f"No data found for {resource_type}")
                    continue
                
                # Save files with unique names
                safe_resource_type = "".join(c for c in resource_type if c.isalnum() or c in ('-', '_'))
                file_timestamp = f"{timestamp}_{len(saved_files):03d}"
                
                parquet_filename = f"{safe_resource_type}{resource_suffix}_{file_timestamp}.parquet"
                parquet_filepath = os.path.join(parquet_dir, parquet_filename)
                
                # Save data
                df = pd.DataFrame([flatten_dict(d) for d in data])
                df.to_parquet(parquet_filepath, index=False, compression='snappy')
                saved_files.append(parquet_filepath)
                
                print(f"Saved {resource_type} data to {parquet_filepath}")
                print(f"Records: {len(df)}")
                
                if include_csv:
                    csv_filename = f"{safe_resource_type}{resource_suffix}_{file_timestamp}.csv"
                    csv_filepath = os.path.join(csv_dir, csv_filename)
                    df.to_csv(csv_filepath, index=False)
                    saved_files.append(csv_filepath)
                    print(f"Saved CSV to {csv_filepath}")
            
            except Exception as e:
                print(f"Error processing file {file_info}: {str(e)}")
                continue

        return saved_files

    def _save_with_pandas(self, data_chunks, parquet_path, csv_dir, resource_type, timestamp):
        """Process data using pandas when Spark is not available"""
        try:
            # Flatten and combine all chunks
            flattened_data = []
            for chunk in data_chunks:
                flattened_data.extend([flatten_dict(d) for d in chunk])
            
            # Convert to DataFrame
            df = pd.DataFrame(flattened_data)
            
            # Save as Parquet with compression
            df.to_parquet(parquet_path, index=False, compression='snappy')
            print(f"Saved {resource_type} data to {parquet_path}")
            print(f"Number of records: {len(df)}")
            
            # Save as CSV if requested
            if csv_dir:
                csv_path = os.path.join(csv_dir, f"{resource_type}_{timestamp}.csv")
                
                # Process CSV conversion in chunks to manage memory
                chunk_size = 100000  # Adjust based on available memory
                num_chunks = len(df) // chunk_size + (1 if len(df) % chunk_size else 0)
                
                for i in range(num_chunks):
                    start_idx = i * chunk_size
                    end_idx = min((i + 1) * chunk_size, len(df))
                    chunk_df = df.iloc[start_idx:end_idx].copy()
                    
                    # Convert complex types to strings
                    for col in chunk_df.columns:
                        chunk_df[col] = chunk_df[col].apply(
                            lambda x: str(x) if isinstance(x, (dict, list)) else x
                        )
                    
                    # Write to CSV
                    mode = 'w' if i == 0 else 'a'
                    header = i == 0
                    chunk_df.to_csv(csv_path, index=False, mode=mode, header=header)
                
                print(f"Saved {resource_type} data to {csv_path}")
                print(f"Number of columns in CSV: {len(df.columns)}")
        
        except Exception as e:
            print(f"Error in pandas processing for {resource_type}: {str(e)}")
            raise 

    def _poll_and_process_job(self, endpoint_name, job_url, output_dir, include_csv):
        """Combined polling and processing to reduce code complexity"""
        try:
            job_status = self._poll_job(job_url)
            if not job_status.get("output"):
                return None

            return self._save_files(job_status["output"], output_dir, include_csv)
        except Exception as e:
            raise Exception(f"Error in job processing for {endpoint_name}: {str(e)}")

    def convert_to_parquet(self, ndjson_path: str, output_dir: str, chunk_size: int = 100000):
        """
        Convert an NDJSON file to Parquet format using chunked processing.
        """
        try:
            base_name = os.path.basename(ndjson_path).replace('.ndjson', '')
            parquet_path = os.path.join(output_dir, f"{base_name}.parquet")
            
            writer = None
            
            for i, chunk in enumerate(pd.read_json(ndjson_path, lines=True, chunksize=chunk_size)):
                table = pa.Table.from_pandas(chunk)
                
                if writer is None:
                    writer = pq.ParquetWriter(parquet_path, table.schema)
                
                writer.write_table(table)
                
                self.logger.info(f"Processed chunk {i+1} for {ndjson_path}")
            
            if writer:
                writer.close()
                self.logger.info(f"Successfully converted {ndjson_path} to {parquet_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to convert {ndjson_path} to Parquet: {str(e)}")
            if writer:
                writer.close()
            raise

    def convert_to_csv(self, ndjson_path: str, output_dir: str, chunk_size: int = 100000):
        """
        Convert an NDJSON file to CSV format using chunked processing.
        """
        try:
            base_name = os.path.basename(ndjson_path).replace('.ndjson', '')
            csv_path = os.path.join(output_dir, f"{base_name}.csv")
            
            first_chunk = True
            for i, chunk in enumerate(pd.read_json(ndjson_path, lines=True, chunksize=chunk_size)):
                chunk.to_csv(csv_path, mode='w' if first_chunk else 'a', 
                           header=first_chunk, index=False)
                first_chunk = False
                
                self.logger.info(f"Processed chunk {i+1} for {ndjson_path}")
            
            self.logger.info(f"Successfully converted {ndjson_path} to {csv_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to convert {ndjson_path} to CSV: {str(e)}")
            raise

    def get_supported_resource_types(self) -> List[str]:
        """
        Get the list of supported resource types based on the environment.
        """
        if self.environment == "sandbox":
            return ["ExplanationOfBenefit", "Patient", "Coverage"]
        return self.config.VALID_RESOURCE_TYPES

    def get_all_data(self, output_dir: str, since: Optional[str] = None, incremental: bool = False) -> Dict[str, List[str]]:
        """
        Download all available data and convert to Parquet and CSV formats.
        
        Args:
            output_dir (str): Directory to store output files
            since (Optional[str]): Starting date for data retrieval (ISO format)
            incremental (bool): If True, use incremental loading strategy
        """
        downloaded_files = {}
        
        # Set up directories
        ndjson_dir = os.path.join(output_dir, "ndjson")
        parquet_dir = os.path.join(output_dir, "parquet")
        csv_dir = os.path.join(output_dir, "csv")
        
        for directory in [ndjson_dir, parquet_dir, csv_dir]:
            os.makedirs(directory, exist_ok=True)
            self.logger.info(f"Created directory: {directory}")

        # Convert 'since' to a proper FHIR Instant if provided (applies to both incremental and full loads)
        if since:
            dt = datetime.fromisoformat(since)
            dt_utc = dt.astimezone(timezone.utc).replace(microsecond=0)
            since = dt_utc.isoformat().replace("+00:00", "Z")
            self.logger.info(f"Starting load from: {since}")

        if incremental:
            # If incremental and no 'since' found, use default
            last_processed = self._get_last_processed_date(output_dir) or since
            if not last_processed:
                self.logger.info("No previous processing date found, defaulting to 30 days ago")
                last_processed = (datetime.now() - timedelta(days=30)).isoformat()
        else:
            last_processed = self._get_last_processed_date(output_dir) or since
            if not last_processed:
                self.logger.info("No previous processing date found, defaulting to 30 days ago")
                last_processed = (datetime.now() - timedelta(days=30)).isoformat()

        for group in ["all"]:
            self.logger.info(f"Processing group: {group}")
            
            job_id = self.start_job(
                f"Group/{group}",
                resource_types=self.get_supported_resource_types(),
                since=since
            )
            
            if job_id is None:
                self.logger.warning("No job started for this group, skipping.")
                downloaded_files[f"Group/{group}"] = []
                continue
            
            job_result = self.wait_for_job(job_id)
            
            group_files = []
            for file_info in job_result.get("output", []):
                resource_type = file_info["type"]
                url = file_info["url"]
                
                # Include timestamp and load type in filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                load_type = "incremental" if incremental else "full"
                filename = f"{group}_{resource_type}_{load_type}_{timestamp}.ndjson"
                ndjson_path = os.path.join(ndjson_dir, filename)
                
                try:
                    self.download_file(url, ndjson_path)
                    self.convert_to_parquet(ndjson_path, parquet_dir)
                    self.convert_to_csv(ndjson_path, csv_dir)
                    
                    group_files.append(ndjson_path)
                    
                except Exception as e:
                    self.logger.error(f"Failed to process file {filename}: {str(e)}")
                    continue
                
            downloaded_files[f"Group/{group}"] = group_files
            
            # Update the last processed date
            if incremental:
                self._update_last_processed_date(output_dir)
        
        return downloaded_files

    def _get_last_processed_date(self, output_dir: str) -> Optional[str]:
        """Get the last processed date from metadata file."""
        metadata_file = os.path.join(output_dir, "load_metadata.json")
        try:
            if os.path.exists(metadata_file):
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    return metadata.get('last_processed_date')
        except Exception as e:
            self.logger.warning(f"Error reading metadata file: {str(e)}")
        return None

    def _update_last_processed_date(self, output_dir: str):
        """Update the last processed date in metadata file."""
        metadata_file = os.path.join(output_dir, "load_metadata.json")
        try:
            metadata = {}
            if os.path.exists(metadata_file):
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
            
            metadata['last_processed_date'] = datetime.now().isoformat()
            metadata['last_update'] = datetime.now().isoformat()
            
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
        except Exception as e:
            self.logger.error(f"Error updating metadata file: {str(e)}")

    def start_job(self, endpoint: str, resource_types: Optional[List[str]] = None, 
                   since: Optional[str] = None) -> Optional[str]:
        """
        Start a new data export job. If certain resource types are unauthorized, remove them and retry
        until none remain or the server accepts them. Returns None if no authorized types remain.
        """
        self._ensure_valid_token()

        if resource_types:
            invalid_types = set(resource_types) - set(self.get_supported_resource_types())
            if invalid_types:
                raise ValueError(f"Invalid resource types: {invalid_types}")

        # Repeat until success or no resource types left
        while resource_types:
            url = urljoin(self.config.base_url, f"/api/v2/{endpoint}/$export")

            query_params = []
            if resource_types:
                query_params.append(f"_type={','.join(resource_types)}")
            if since:
                query_params.append(f"_since={since}")

            if query_params:
                url = f"{url}?{'&'.join(query_params)}"

            headers = {
                "Accept": "application/fhir+json",
                "Prefer": "respond-async",
                "Authorization": f"Bearer {self.access_token}"
            }

            try:
                self.logger.info(f"Starting job with URL: {url}")
                response = requests.get(url, headers=headers)
                self.logger.info(f"Response status: {response.status_code}")
                self.logger.info(f"Response headers: {dict(response.headers)}")

                response.raise_for_status()

                job_url = response.headers.get("Content-Location")
                if not job_url:
                    raise RuntimeError("No Content-Location header in response")
                job_id = job_url.split("/")[-1]
                
                self.logger.info(f"Started job {job_id} for endpoint {endpoint}")
                return job_id  # Success

            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 400:
                    body_text = e.response.text
                    # Identify any resource types flagged as unauthorized
                    removed = False
                    for r_type in list(resource_types):
                        if f"unauthorized resource type {r_type}" in body_text:
                            self.logger.warning(f"Removing unauthorized resource type: {r_type}")
                            resource_types.remove(r_type)
                            removed = True
                    if removed:
                        # If we removed something, try again
                        continue

                # If we arrive here, it's a non-recoverable 400 or another error
                self.logger.error(f"Failed to start job: {str(e)}")
                if hasattr(e.response, 'text'):
                    self.logger.error(f"Response text: {e.response.text}")
                raise

        # If no resource types remain, skip the job without error
        self.logger.warning("No authorized resource types remain. Skipping job.")
        return None

    def _ensure_valid_token(self):
        """Ensure we have a valid access token."""
        if not self.access_token or datetime.now().timestamp() >= self.token_expiry:
            self.authenticate() 

    def wait_for_job(self, job_id: str, check_interval: int = 5, 
                    timeout: Optional[int] = None) -> Dict:
        """
        Wait for a job to complete.
        
        Args:
            job_id (str): Job ID to wait for
            check_interval (int): Seconds to wait between status checks
            timeout (int, optional): Maximum seconds to wait
            
        Returns:
            dict: Completed job information
        """
        start_time = time.time()
        
        while True:
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")
                
            status = self.check_job_status(job_id)
            
            # Log status for debugging
            self.logger.info(f"Job {job_id} status: {status}")
            
            if status.get("status") == "in-progress":
                self.logger.info(f"Job {job_id} still processing, waiting {check_interval} seconds...")
                time.sleep(check_interval)
                continue
                
            # Check for errors
            if "error" in status and status["error"]:
                # If we have error files, download and log them
                if isinstance(status["error"], list):
                    error_messages = []
                    for error_file in status["error"]:
                        if isinstance(error_file, dict) and error_file.get("type") == "OperationOutcome":
                            try:
                                # Download the error file
                                error_content = self._download_error_file(error_file["url"])
                                error_messages.append(error_content)
                            except Exception as e:
                                self.logger.error(f"Failed to download error file: {str(e)}")
                                error_messages.append(str(error_file))
                    
                    if error_messages:
                        # Check if these are "soft" errors we can continue with
                        if all("Error retrieving BlueButton ID" in msg for msg in error_messages):
                            self.logger.warning(f"Job {job_id} completed with warnings: \n" + "\n".join(error_messages))
                            return status
                        raise RuntimeError(f"Job {job_id} failed with errors:\n" + "\n".join(error_messages))
                
                raise RuntimeError(f"Job {job_id} failed: {status['error']}")
                
            # If we have output and no errors, job is complete
            if "output" in status and isinstance(status["output"], list):
                self.logger.info(f"Job {job_id} completed successfully")
                return status
                
            self.logger.warning(f"Unknown job status: {status}")
            time.sleep(check_interval)

    def check_job_status(self, job_id: str) -> Dict:
        """
        Check the status of a job.
        
        Args:
            job_id (str): Job ID to check
            
        Returns:
            dict: Job status information
        """
        self._ensure_valid_token()
        
        url = urljoin(self.config.base_url, f"/api/v2/jobs/{job_id}")
        headers = {
            "Accept": "application/fhir+json",
            "Authorization": f"Bearer {self.access_token}"
        }
        
        try:
            response = self._make_request("GET", url, headers=headers)
            
            # Log response details for debugging
            self.logger.info(f"Job status response status: {response.status_code}")
            self.logger.info(f"Job status response headers: {dict(response.headers)}")
            
            # Check if we got a 202 (still processing)
            if response.status_code == 202:
                return {"status": "in-progress"}
                
            # If we get here, job should be complete
            try:
                return response.json()
            except ValueError:
                # If response isn't JSON, check for X-Progress header
                progress = response.headers.get("X-Progress")
                if progress:
                    return {"status": "in-progress", "progress": progress}
                # If no progress header, check if we have output URLs in the response
                if "output" in response.text:
                    return {"status": "completed", "output": response.text}
                return {"status": "unknown", "response": response.text}
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to check job status: {str(e)}")
            if hasattr(e.response, 'text'):
                self.logger.error(f"Response text: {e.response.text}")
            raise

    def _download_error_file(self, url: str) -> str:
        """
        Download and parse an error file.
        
        Args:
            url (str): URL of the error file
            
        Returns:
            str: Parsed error message
        """
        self._ensure_valid_token()
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/fhir+json"
        }
        
        try:
            response = self._make_request("GET", url, headers=headers)
            error_data = response.json()
            
            # Parse OperationOutcome resource
            if isinstance(error_data, list):
                error_data = error_data[0]
                
            if error_data.get("resourceType") == "OperationOutcome":
                issues = error_data.get("issue", [])
                error_messages = []
                for issue in issues:
                    if "diagnostics" in issue:
                        error_messages.append(issue["diagnostics"])
                    elif "details" in issue and "text" in issue["details"]:
                        error_messages.append(issue["details"]["text"])
                
                if error_messages:
                    return "\n".join(error_messages)
                
            return str(error_data)
            
        except Exception as e:
            self.logger.error(f"Failed to parse error file: {str(e)}")
            return f"Failed to parse error file: {str(e)}"

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Make an HTTP request with retry logic and session reuse to improve performance.
        """
        for attempt in range(self.config.max_retries):
            try:
                # Using the Session for better connection reuse
                with self.session.request(method, url, timeout=self.config.timeout, **kwargs) as response:
                    response.raise_for_status()
                    return response
            except requests.exceptions.RequestException as e:
                if attempt < self.config.max_retries - 1:
                    self.logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.config.max_retries}): {str(e)}. "
                        f"Retrying in {self.config.retry_delay} seconds..."
                    )
                    time.sleep(self.config.retry_delay)
                else:
                    # No more retries left, re-raise the exception
                    raise 

    def download_file(self, url: str, output_path: str, chunk_size: int = 1024 * 1024):
        """
        Download a file from the specified URL using streaming.
        
        Args:
            url (str): URL to download from
            output_path (str): Where to save the file
            chunk_size (int): Size of chunks to download (default: 1MB)
        """
        self._ensure_valid_token()
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept-Encoding": "gzip"
        }
        
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Use a temporary file during download
            temp_path = output_path + '.tmp'
            
            with self.session.get(url, headers=headers, stream=True) as response:
                response.raise_for_status()
                
                with open(temp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:  # Filter out keep-alive chunks
                            f.write(chunk)
                            
            # Rename temp file to final name after successful download
            os.rename(temp_path, output_path)
            
            self.logger.info(f"Successfully downloaded file to {output_path}")
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to download file: {str(e)}")
            # Clean up temp file if it exists
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise 

    def get_server_metadata(self) -> Dict:
        """
        Retrieve server metadata from '/api/v2/metadata'.
        Useful for discovering supported features and capabilities.
        """
        self._ensure_valid_token()
        url = urljoin(self.config.base_url, "/api/v2/metadata")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
        try:
            response = self._make_request("GET", url, headers=headers)
            metadata = response.json()
            self.logger.info("Fetched server metadata successfully.")
            return metadata
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to fetch server metadata: {str(e)}")
            raise

    def list_jobs(self) -> List[Dict]:
        """
        List all jobs via '/api/v2/jobs'.
        Returns:
            A list of job info dictionaries, or an empty list on error.
        """
        self._ensure_valid_token()
        url = urljoin(self.config.base_url, "/api/v2/jobs")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/fhir+json"
        }
        try:
            response = self._make_request("GET", url, headers=headers)
            job_list = response.json()
            self.logger.info(f"Found {len(job_list)} existing job(s).")
            return job_list if isinstance(job_list, list) else []
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to list jobs: {str(e)}")
            return []

    def check_accessible_resource_types(self, candidate_types: List[str]) -> List[str]:
        """
        Quick-check a list of resource types and return those that do NOT
        immediately throw a 400 unauthorized resource error.
        This does NOT remove from the main code, just returns the accessible subset.
        """
        accessible = []
        for r_type in candidate_types:
            try:
                # We'll do a dry-run with start_job using only r_type
                job_id = self.start_job("Group/all", [r_type])
                if job_id is not None:
                    accessible.append(r_type)
            except requests.exceptions.HTTPError as e:
                self.logger.warning(f"{r_type} appears unauthorized or invalid: {str(e)}")
        return accessible 