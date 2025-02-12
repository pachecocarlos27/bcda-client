class BCDAConfig:
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
            "Attribution_Status": f"{self.base_url}/api/v2/attribution_status"
        }
        
        self.resource_types = {
            "Patient": "Patient,ExplanationOfBenefit,Coverage",
            "Group_All": "ExplanationOfBenefit,Patient,Coverage",
            "Group_Runout": "ExplanationOfBenefit,Patient,Coverage"
        }
        
        self.poll_interval = 5 