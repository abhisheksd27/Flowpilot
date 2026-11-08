"""Swappable LLM clients with provider-aware caching, usage counters, and backoff."""
from abc import ABC, abstractmethod
import json
import time
from typing import Any
import requests
from config import Settings
from tools.cache import DiskCache, digest


class LLMClient(ABC):
    """Small interface also implemented by the deterministic test double."""

    metrics: dict[str, int]

    @abstractmethod
    def complete(self, system: str, prompt: str, *, json_mode: bool = True) -> str:
        """Return model text or raise a bounded, actionable exception."""


class HTTPClient(LLMClient):
    """Shared cache and transport for provider-specific wire formats."""

    provider = ""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache = DiskCache(settings.data_dir / "cache/llm", settings.llm_cache_ttl)
        self.metrics = {"calls": 0, "cache_hits": 0, "input_tokens": 0,
                        "output_tokens": 0, "retries": 0}

    @abstractmethod
    def request(self, messages: list[dict], json_mode: bool) -> tuple[str, dict, dict]:
        """Return URL, headers, and body without exposing them to logs."""

    def decode(self, data: dict) -> tuple[str, int, int]:
        """Decode the OpenAI-compatible response."""
        usage = data.get("usage", {})
        return (data["choices"][0]["message"]["content"], usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0))

    def complete(self, system: str, prompt: str, *, json_mode: bool = True) -> str:
        """Cache successful text; retry 429, 5xx, network failures, and invalid JSON."""
        url, headers, body = self.request([
            {"role": "system", "content": system}, {"role": "user", "content": prompt}
        ], json_mode)
        key = digest([self.provider, url, body])
        cached = self.cache.get(key)
        if cached is not None:
            self.metrics["cache_hits"] += 1
            return cached
        for attempt in range(self.settings.max_retries + 1):
            try:
                self.metrics["calls"] += 1
                response = requests.post(url, headers=headers, json=body,
                                         timeout=max(60, self.settings.http_timeout),
                                         allow_redirects=False)
                if 300 <= response.status_code < 400:
                    raise ValueError("LLM redirects are forbidden")
                response.raise_for_status()
                result, incoming, outgoing = self.decode(response.json())
                self.metrics["input_tokens"] += incoming
                self.metrics["output_tokens"] += outgoing
                if not isinstance(result, str) or not result.strip():
                    raise ValueError("Empty model response")
                if json_mode:
                    json.loads(result)
                self.cache.put(key, result)
                return result
            except (requests.RequestException, ValueError, KeyError, IndexError) as error:
                status = getattr(getattr(error, "response", None), "status_code", None)
                if status and 400 <= status < 500 and status != 429:
                    raise RuntimeError(f"{self.provider}: HTTP {status}; check model and API key") from None
                if attempt == self.settings.max_retries:
                    raise RuntimeError(f"{self.provider}: request failed ({type(error).__name__})") from None
                self.metrics["retries"] += 1
                time.sleep(self.settings.backoff_seconds * 2 ** attempt)
        raise RuntimeError("Unreachable retry state")


class GeminiClient(HTTPClient):
    """Gemini's OpenAI-compatible free-tier endpoint."""

    provider = "gemini"

    def request(self, messages: list[dict], json_mode: bool) -> tuple[str, dict, dict]:
        if not self.settings.gemini_key:
            raise ValueError("Set GEMINI_API_KEY in .env")
        body = {"model": self.settings.gemini_model, "messages": messages, "temperature": 0.1}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                {"Authorization": f"Bearer {self.settings.gemini_key}"}, body)


class GroqClient(GeminiClient):
    """Groq's OpenAI-compatible endpoint."""

    provider = "groq"

    def request(self, messages: list[dict], json_mode: bool) -> tuple[str, dict, dict]:
        if not self.settings.groq_key:
            raise ValueError("Set GROQ_API_KEY in .env")
        body = {"model": self.settings.groq_model, "messages": messages, "temperature": 0.1}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return ("https://api.groq.com/openai/v1/chat/completions",
                {"Authorization": f"Bearer {self.settings.groq_key}"}, body)


class OllamaClient(HTTPClient):
    """Local Ollama chat API; no API key or hosted account required."""

    provider = "ollama"

    def request(self, messages: list[dict], json_mode: bool) -> tuple[str, dict, dict]:
        body = {"model": self.settings.ollama_model, "messages": messages,
                "stream": False, "options": {"temperature": 0}}
        if json_mode:
            body["format"] = "json"
        return self.settings.ollama_url.rstrip("/") + "/api/chat", {}, body

    def decode(self, data: dict) -> tuple[str, int, int]:
        return data["message"]["content"], data.get("prompt_eval_count", 0), data.get("eval_count", 0)


class BuiltinClient(LLMClient):
    """Deterministic production rules for the supported environmental pipeline.

    This is explicitly not an LLM and makes no inference-quality claim.
    It implements the same interface so automatic runs need no paid services.
    """
    def __init__(self, settings: Settings):
        self.metrics = {"calls": 0, "cache_hits": 0, "input_tokens": 0,
                        "output_tokens": 0, "retries": 0}

    def complete(self, system: str, prompt: str, *, json_mode: bool = True) -> str:
        from pipeline.contracts import default_plan
        payload = json.loads(prompt)
        self.metrics["calls"] += 1
        if payload["task"] == "plan":
            return json.dumps(default_plan(payload["request"]))
        if payload["task"] == "generate_code":
            return payload["reference_code"]
        return json.dumps({"code": payload["reference_code"], "diagnosis": payload["diagnosis"]})


def make_client(settings: Settings) -> LLMClient:
    """Select explicit built-in rules or one of the three real model providers."""
    providers = {"builtin": BuiltinClient, "gemini": GeminiClient,
                 "groq": GroqClient, "ollama": OllamaClient}
    if settings.provider not in providers:
        raise ValueError(f"Unknown provider: {settings.provider}")
    return providers[settings.provider](settings)
