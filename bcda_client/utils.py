import datetime
import os
import pandas as pd

def get_default_since_date():
    thirty_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30))
    return thirty_days_ago.strftime("%Y-%m-%dT%H:%M:%S.000Z")

def flatten_dict(d, parent_key='', sep='_'):
    # Pre-allocate items list with an estimated size
    items = []
    
    # Move common operations outside the loop
    join_str = str.join
    str_conv = str
    
    def _flatten(d, parent_key=''):
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            
            if isinstance(v, dict):
                _flatten(v, new_key)
            elif isinstance(v, list):
                if v and isinstance(v[0], dict):
                    # Process FHIR-like structures more efficiently
                    for i, item in enumerate(v):
                        indexed_key = f"{new_key}_{i}"
                        
                        # Handle special FHIR fields in one block
                        special_fields = {
                            'system': 'system',
                            'value': 'value',
                            'code': 'code',
                            'display': 'display'
                        }
                        
                        # Process nested dictionary
                        _flatten(item, indexed_key)
                        
                        # Add special fields if they exist
                        for field, suffix in special_fields.items():
                            if field in item:
                                items.append((f"{new_key}_{suffix}", item[field]))
                else:
                    # Join list elements more efficiently
                    items.append((new_key, join_str('|', map(str_conv, v)) if v else ''))
            else:
                items.append((new_key, str_conv(v) if v is not None else ''))
    
    _flatten(d)
    return dict(items)

def print_data_summary(base_dir):
    print("\n=== Data Download Summary ===")
    parquet_dir = os.path.join(base_dir, "parquet")
    
    if not os.path.exists(parquet_dir):
        print("No data directory found")
        return
        
    files = os.listdir(parquet_dir)
    print(f"\nFiles in {parquet_dir}:")
    
    for file in files:
        if file.endswith('.parquet'):
            filepath = os.path.join(parquet_dir, file)
            df = pd.read_parquet(filepath)
            print(f"\n{file}:")
            print(f"  Records: {len(df)}")
            if 'resourceType' in df.columns:
                print(f"  Resource Types: {df['resourceType'].unique()}") 