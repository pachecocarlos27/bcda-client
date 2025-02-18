class BCDAConfig:
    # Add these constants
    VALID_ENVIRONMENTS = ["sandbox", "production"]
    VALID_RESOURCE_TYPES = [
        "ExplanationOfBenefit",
        "Patient",
        "Coverage",
        "Claim",
        "ClaimResponse"
    ]
    
    def __init__(self, client_id, client_secret, base_url=None, is_sandbox=True):
        self.client_id = client_id
        self.client_secret = client_secret
        
        if base_url:
            self.base_url = base_url
        else:
            self.base_url = "https://sandbox.bcda.cms.gov" if is_sandbox else "https://api.bcda.cms.gov"
            
        self.auth_endpoint = f"{self.base_url}/auth/token"
        self.export_endpoints = {
            "Metadata": f"{self.base_url}/api/v2/metadata",
            "Patient": f"{self.base_url}/api/v2/Patient/$export",
            "Group_All": f"{self.base_url}/api/v2/Group/all/$export",
            "Group_Runout": f"{self.base_url}/api/v2/Group/runout/$export",
            "Jobs": f"{self.base_url}/api/v2/jobs",
            "Attribution_Status": f"{self.base_url}/api/v2/attribution_status",
            "Group_Claims": f"{self.base_url}/api/v2/Group/all/$export"
        }
        
        # Define endpoint-specific resource types based on successful jobs
        self.endpoint_resource_types = {
            "Patient": None,  # Don't specify type for Patient endpoint
            "Group_All": None,  # Don't specify type for Group endpoints
            "Group_Runout": None,
            "Group_Claims": None
        }
        
        # Define endpoint-specific parameters
        self.endpoint_params = {
            "Group_All": {
                "_since": "2023-01-01T00:00:00.000-05:00"  # Use 2023 date
            },
            "Group_Runout": {
                "_since": "2023-01-01T00:00:00.000-05:00"  # Use 2023 date
            },
            "Patient": {
                "_since": "2023-01-01T00:00:00.000-05:00"  # Use 2023 date
            }
        }
        
        # General resource types to try
        self.resource_types_to_try = [
            None,  # Try without type specification first
            "ExplanationOfBenefit",
            "Patient",
            "Coverage"
        ]
        
        # Headers configuration per documentation
        self.endpoint_headers = {
            "Jobs": {
                "Accept": "application/fhir+json",
                "Prefer": "respond-async"
            },
            "default": {
                "Accept": "application/fhir+json"
            },
            "bulk": {
                "Accept": "application/fhir+json",
                "Prefer": "respond-async"
            }
        }
        
        self.poll_interval = 60  # Initial polling interval to 1 minute
        self.max_concurrent_jobs = 3  # Maximum concurrent bulk export jobs
        self.max_poll_time = 30  # Maximum polling time in minutes
        
        # Add timeout and retry settings
        self.timeout = 30  # seconds
        self.max_retries = 3
        self.retry_delay = 5  # seconds 