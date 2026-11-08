"""Allowlisted, size-bounded Open-Meteo HTTP access with retries and caching."""
import json
import time
from typing import Any
from urllib.parse import urlsplit
import requests
from config import Settings
from tools.cache import DiskCache, digest

ALLOWED_ENDPOINTS = {"api.open-meteo.com": "/v1/forecast",
                     "air-quality-api.open-meteo.com": "/v1/air-quality",
                     "geocoding-api.open-meteo.com": "/v1/search"}


def check_url(url: str) -> None:
    """Only exact HTTPS catalog endpoints; never follow redirects."""
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_ENDPOINTS
        or parsed.port not in (None, 443) or parsed.username or parsed.password
        or parsed.query or parsed.fragment or parsed.path != ALLOWED_ENDPOINTS.get(parsed.hostname)):
        raise ValueError("URL must be an exact HTTPS endpoint from the API catalog")


class APITool:
    """Reusable broker with injected transport for key-free deterministic tests."""
    def __init__(self, settings: Settings, session: Any = None):
        self.settings = settings
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.cache = DiskCache(settings.data_dir / "cache/api", settings.api_cache_ttl)
        self.metrics = {"requests": 0, "cache_hits": 0, "retries": 0}

    def call_api(self, url: str, params: dict[str, Any], *, refresh: bool = False) -> dict:
        """Retry transient failures and malformed bodies, never caching a failed response."""
        check_url(url)
        allowed = {"name", "count", "language", "format"} if "geocoding" in url else {
            "latitude", "longitude", "hourly", "past_days", "forecast_days", "timezone"}
        if set(params) - allowed:
            raise ValueError("API parameters outside the supported catalog")
        key = digest([url, params])
        cached = None if refresh else self.cache.get(key)
        if isinstance(cached, dict):
            self.metrics["cache_hits"] += 1
            return cached
        for attempt in range(self.settings.max_retries + 1):
            try:
                self.metrics["requests"] += 1
                with self.session.get(url, params=params, timeout=self.settings.http_timeout,
                                      allow_redirects=False, stream=True) as response:
                    if 300 <= response.status_code < 400:
                        raise PermissionError("API redirects are forbidden")
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > 5_000_000:
                            raise PermissionError("API response exceeds 5 MB")
                        chunks.append(chunk)
                    payload = json.loads(b"".join(chunks))
                if not isinstance(payload, dict) or payload.get("error"):
                    raise ValueError("API returned an invalid object or error")
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


def call_api(url: str, params: dict[str, Any], settings: Settings | None = None) -> dict:
    return APITool(settings or Settings.from_env()).call_api(url, params)
