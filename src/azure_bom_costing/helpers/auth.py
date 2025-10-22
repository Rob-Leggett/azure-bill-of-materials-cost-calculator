import requests

MGMT_SCOPE = "https://management.azure.com/.default"

# ---------- AAD token for Enterprise API ----------
def get_aad_token(tenant_id: str, client_id: str, client_secret: str, scope: str = MGMT_SCOPE) -> str:
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
        "grant_type": "client_credentials",
    }
    r = requests.post(token_url, data=data, timeout=60)
    r.raise_for_status()
    return r.json()["access_token"]