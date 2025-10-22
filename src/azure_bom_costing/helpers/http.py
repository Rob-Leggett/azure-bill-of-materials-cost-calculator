from typing import Optional, Dict

import requests

# ---------- HTTP helpers ----------
def http_get_json(url: str, headers: Optional[Dict[str, str]] = None) -> dict:
    """HTTP GET a JSON endpoint and return the decoded JSON.

    Raises:
        requests.HTTPError on non-2xx responses.
    """
    r = requests.get(url, headers=headers or {}, timeout=60)
    r.raise_for_status()
    return r.json()


def http_get(url: str, headers: Optional[Dict[str, str]] = None) -> requests.Response:
    """HTTP GET a resource and return the raw Response (stream enabled).

    Useful for large payloads/files. Caller is responsible for consuming
    and closing the stream if needed.

    Raises:
        requests.HTTPError on non-2xx responses.
    """
    r = requests.get(url, headers=headers or {}, timeout=300, stream=True)
    r.raise_for_status()
    return r

def get_session() -> requests.Session:
    return requests.Session()