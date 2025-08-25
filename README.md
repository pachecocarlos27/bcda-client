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

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">
Made with ❤️ by <a href="https://github.com/pachecocarlos27">Carlos Pacheco</a>
</div>
