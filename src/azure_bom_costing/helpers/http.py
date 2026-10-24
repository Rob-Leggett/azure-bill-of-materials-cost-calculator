
from typing import Any, cast

import requests


# ---------- HTTP helpers ----------
def http_get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """HTTP GET a JSON endpoint and return the decoded JSON.

    Raises:
        requests.HTTPError on non-2xx responses.
    """
    r = requests.get(url, headers=headers or {}, timeout=60)
    r.raise_for_status()
    return cast(dict[str, Any], r.json())


def http_get(url: str, headers: dict[str, str] | None = None) -> requests.Response:
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