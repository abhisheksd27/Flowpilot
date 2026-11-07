"""HTTPS-only Open-Meteo API broker with bounded retries and disk caching."""
import time
from typing import Any
from urllib.parse import urlsplit
import requests
from config import Settings
from tools.cache import DiskCache, digest

ALLOWED_ENDPOINTS = {
    "api.open-meteo.com": "/v1/forecast",
    "air-quality-api.open-meteo.com": "/v1/air-quality",
    "geocoding-api.open-meteo.com": "/v1/search",
}


def check_url(url: str) -> None:
    """Reject credentials, ports, query strings, fragments, and noncatalog endpoints."""
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_ENDPOINTS
            or parsed.port not in (None, 443) or parsed.username or parsed.password
            or parsed.query or parsed.fragment
            or parsed.path != ALLOWED_ENDPOINTS.get(parsed.hostname)):
        raise ValueError("URL must be an exact HTTPS endpoint from the API catalog")


class APITool:
    """Reusable API session with counters exposed to the run logger."""

    def __init__(self, settings: Settings, session: Any = None):
        self.settings = settings
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.cache = DiskCache(settings.data_dir / "cache/api", settings.api_cache_ttl)
        self.metrics = {"requests": 0, "cache_hits": 0, "retries": 0}

    def call_api(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch JSON, never following redirects; retry transient or malformed responses."""
        check_url(url)
        key = digest([url, params])
        cached = self.cache.get(key)
        if cached is not None:
            self.metrics["cache_hits"] += 1
            return cached
        for attempt in range(self.settings.max_retries + 1):
            try:
                self.metrics["requests"] += 1
                response = self.session.get(url, params=params, timeout=self.settings.http_timeout,
                                            allow_redirects=False)
                if 300 <= response.status_code < 400:
                    raise ValueError("API redirects are forbidden")
                response.raise_for_status()
                if len(response.content) > 5_000_000:
                    raise ValueError("API response exceeds 5 MB")
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("error"):
                    raise ValueError("API returned an invalid object or an error")
                self.cache.put(key, payload)
                return payload
            except (requests.RequestException, ValueError) as error:
                status = getattr(getattr(error, "response", None), "status_code", None)
                if status and 400 <= status < 500 and status != 429:
                    raise
                if attempt == self.settings.max_retries:
                    raise
                self.metrics["retries"] += 1
                time.sleep(self.settings.backoff_seconds * 2 ** attempt)
        raise RuntimeError("Unreachable retry state")


def call_api(url: str, params: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Convenience entry point using environment configuration."""
    return APITool(settings or Settings.from_env()).call_api(url, params)
