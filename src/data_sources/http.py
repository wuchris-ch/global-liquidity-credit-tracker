"""Shared HTTP session configuration for public market-data downloads."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def retrying_session() -> requests.Session:
    """Return a GET-only session with bounded retries for transient failures."""
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
