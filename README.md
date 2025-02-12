# BCDA Client

A Python client for the CMS Beneficiary Claims Data API (BCDA).

## Installation

bash
pip install bcda-client

## Quick Start

python
from bcda_client import BCDAClient
Initialize client (Sandbox)
client = BCDAClient(
client_id="your_client_id",
client_secret="your_client_secret",
is_sandbox=True
)
Download data
results = client.download_data(
output_dir="my_data",
include_csv=True,
incremental=False
)

## Features

- Support for both sandbox and production environments
- Automatic authentication handling
- Support for all BCDA endpoints:
  - Metadata
  - Patient
  - Group (all and runout)
  - Jobs
  - Attribution Status
- Data export in both Parquet and CSV formats
- Support for incremental and full extracts
- Automatic flattening of nested FHIR structures

## Configuration

### Environment Options

Sandbox Environment
client = BCDAClient(
client_id="your_client_id",
client_secret="your_client_secret",
is_sandbox=True
)
Production Environment
client = BCDAClient(
client_id="your_client_id",
client_secret="your_client_secret",
is_sandbox=False
)
Custom Environment
client = BCDAClient(
client_id="your_client_id",
client_secret="your_client_secret",
base_url="https://custom.bcda.url"
)

### Download Options
Full extract with CSV
client.download_data(
output_dir="my_data",
include_csv=True,
incremental=False
)
Incremental extract (last 30 days)
client.download_data(
output_dir="my_data",
include_csv=True,
incremental=True
)

## Output Structure

my_data/
├── parquet/
│ ├── Patient_20240211_134435.parquet
│ ├── Coverage_20240211_134435.parquet
│ └── ExplanationOfBenefit_20240211_134435.parquet
└── csv/
├── Patient_20240211_134435.csv
├── Coverage_20240211_134435.csv
└── ExplanationOfBenefit_20240211_134435.csv

## License

MIT License

