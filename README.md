# BCDA Client

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub Issues](https://img.shields.io/github/issues/pachecocarlos27/bcda-client.svg)](https://github.com/pachecocarlos27/bcda-client/issues)
[![GitHub Stars](https://img.shields.io/github/stars/pachecocarlos27/bcda-client.svg)](https://github.com/pachecocarlos27/bcda-client/stargazers)

A comprehensive Python client library for interacting with the Beneficiary Claims Data API (BCDA), designed to simplify healthcare data access and processing for Medicare Advantage Organizations and ACO REACH participants.

## 🎯 Features

- **🔐 Secure Authentication**: Built-in OAuth2 authentication handling
- **📦 Bulk Data Export**: Efficient handling of FHIR bulk data exports
- **🔄 Automatic Retries**: Smart retry logic for network failures
- **📊 Data Processing**: Built-in utilities for processing FHIR resources
- **🚀 Async Support**: Asynchronous operations for better performance
- **📝 Comprehensive Logging**: Detailed logging for debugging and monitoring
- **✅ Type Hints**: Full type annotation support for better IDE integration

## 📋 Table of Contents

- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [Usage Examples](#-usage-examples)
- [API Reference](#-api-reference)
- [Contributing](#-contributing)
- [License](#-license)

## 🚀 Installation

```bash
# Using pip
pip install bcda-client

# Using poetry
poetry add bcda-client

# From source
git clone https://github.com/pachecocarlos27/bcda-client.git
cd bcda-client
pip install -e .
```

## 🏃 Quick Start

```python
from bcda_client import BCDAClient
from bcda_client.models import ExportType

# Initialize the client
client = BCDAClient(
    client_id="your-client-id",
    client_secret="your-client-secret",
    environment="sandbox"  # or "production"
)

# Authenticate
client.authenticate()

# Start a bulk export job
job_url = client.start_bulk_export(
    export_type=ExportType.PATIENT,
    since="2024-01-01",
    resource_types=["Patient", "Coverage", "ExplanationOfBenefit"]
)

# Check job status
status = client.get_job_status(job_url)

# Download data when ready
if status.is_complete:
    files = client.download_all_files(status.output_files)
```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in your project root:

```env
BCDA_CLIENT_ID=your-client-id
BCDA_CLIENT_SECRET=your-client-secret
BCDA_ENVIRONMENT=sandbox
BCDA_API_VERSION=v2
BCDA_TIMEOUT=300
BCDA_MAX_RETRIES=3
```

### Configuration Object

```python
from bcda_client import BCDAClient, BCDAConfig

config = BCDAConfig(
    client_id="your-client-id",
    client_secret="your-client-secret",
    environment="sandbox",
    api_version="v2",
    timeout=300,
    max_retries=3,
    log_level="INFO"
)

client = BCDAClient(config=config)
```

## 📚 Usage Examples

### Basic Export

```python
# Export all data for your ACO
job_url = client.start_bulk_export()

# Wait for completion and download
files = client.export_and_download(
    export_type=ExportType.PATIENT,
    output_dir="./data/exports"
)
```

### Filtered Export

```python
# Export specific resource types since a date
job_url = client.start_bulk_export(
    export_type=ExportType.GROUP,
    since="2024-01-01T00:00:00Z",
    resource_types=["Patient", "Coverage"],
    output_format="ndjson"
)
```

### Async Operations

```python
import asyncio
from bcda_client import AsyncBCDAClient

async def main():
    async with AsyncBCDAClient(config=config) as client:
        await client.authenticate()
        
        # Start multiple export jobs
        jobs = await asyncio.gather(
            client.start_bulk_export(export_type=ExportType.PATIENT),
            client.start_bulk_export(export_type=ExportType.COVERAGE)
        )
        
        # Process results
        for job_url in jobs:
            status = await client.get_job_status(job_url)
            print(f"Job {job_url}: {status.status}")

asyncio.run(main())
```

### Error Handling

```python
from bcda_client.exceptions import (
    BCDAAuthenticationError,
    BCDAExportError,
    BCDATimeoutError
)

try:
    client.authenticate()
    job_url = client.start_bulk_export()
except BCDAAuthenticationError as e:
    print(f"Authentication failed: {e}")
except BCDAExportError as e:
    print(f"Export failed: {e}")
except BCDATimeoutError as e:
    print(f"Request timed out: {e}")
```

## 📖 API Reference

### BCDAClient

#### Methods

- `authenticate()` - Authenticate with BCDA API
- `start_bulk_export(**kwargs)` - Start a new bulk export job
- `get_job_status(job_url)` - Check the status of an export job
- `cancel_job(job_url)` - Cancel a running export job
- `download_file(file_url, output_path)` - Download a single export file
- `download_all_files(file_urls, output_dir)` - Download multiple files
- `export_and_download(**kwargs)` - Combined export and download operation

### Models

- `ExportType` - Enum for export types (PATIENT, COVERAGE, GROUP)
- `JobStatus` - Export job status information
- `ExportFile` - Individual file information
- `BCDAConfig` - Client configuration

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/pachecocarlos27/bcda-client.git
cd bcda-client

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Run linting
flake8 bcda_client/
mypy bcda_client/
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=bcda_client

# Run specific test file
pytest tests/test_client.py
```

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- CMS for providing the BCDA API
- FHIR community for the bulk data standards
- All contributors to this project

## 📞 Support

- 📧 Email: carlos.pacheco@example.com
- 🐛 Issues: [GitHub Issues](https://github.com/pachecocarlos27/bcda-client/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/pachecocarlos27/bcda-client/discussions)

---

<div align="center">
Made with ❤️ by <a href="https://github.com/pachecocarlos27">Carlos Pacheco</a>
</div>
