"""Validated configuration shared by interactive and scheduled pipelines."""
from dataclasses import dataclass, field
from pathlib import Path
import math
import os
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DEFAULT_REQUEST = "Track daily weather and air quality for Bengaluru and flag anomalies."


@dataclass(frozen=True)
class Settings:
    """Runtime configuration. Credentials never appear in repr or run logs."""
    data_dir: Path = ROOT / "data"
    provider: str = "builtin"
    gemini_key: str = field(default="", repr=False)
    groq_key: str = field(default="", repr=False)
    gemini_model: str = "gemini-3.8-flash"
    groq_model: str = "llama-3.3-70b-versatile"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_url: str = "http://localhost:11434"
    api_cache_ttl: int = 900
    llm_cache_ttl: int = 86400
    http_timeout: float = 20
    backoff_seconds: float = 1
    sandbox_backend: str = "auto"
    sandbox_image: str = "agent-de-sandbox:local"
    max_retries: int = 3
    python_timeout: int = 30
    schedule_frequency: str = "hourly"
    schedule_time: str = "08:00"
    schedule_timezone: str = "Asia/Kolkata"

    def __post_init__(self) -> None:
        if self.provider not in {"builtin", "gemini", "groq", "ollama"}:
            raise ValueError("Provider must be builtin, gemini, groq, or ollama")
        if not 0 <= self.max_retries <= 3 or not 1 <= self.python_timeout <= 30:
            raise ValueError("Maximum retries is 3 and execution timeout is 1..30 seconds")
        if min(self.api_cache_ttl, self.llm_cache_ttl, self.backoff_seconds) < 0:
            raise ValueError("Cache lifetimes and backoff must be nonnegative")
        if not math.isfinite(self.http_timeout) or self.http_timeout <= 0:
            raise ValueError("HTTP_TIMEOUT must be finite and positive")
        if not math.isfinite(self.backoff_seconds):
            raise ValueError("BACKOFF_SECONDS must be finite")
        if self.schedule_frequency not in {"hourly", "daily"}:
            raise ValueError("SCHEDULE_FREQUENCY must be hourly or daily")
        hour, minute = map(int, self.schedule_time.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError("SCHEDULE_TIME must be HH:MM")
        ZoneInfo(self.schedule_timezone)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "pipeline.duckdb"

    @classmethod
    def from_env(cls) -> "Settings":
        """Shell variables override the project-local .env."""
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
        kwargs = {}
        for name, item in cls.__dataclass_fields__.items():
            variable = {"provider": "LLM_PROVIDER", "gemini_key": "GEMINI_API_KEY",
                        "groq_key": "GROQ_API_KEY"}.get(name, name.upper())
            if variable in os.environ:
                raw = os.environ[variable].strip()
                default = item.default
                kwargs[name] = (float(raw) if name in {"http_timeout", "backoff_seconds"}
                                else int(raw) if isinstance(default, int) else raw)
        data = Path(kwargs.get("data_dir", ROOT / "data")).expanduser()
        kwargs["data_dir"] = (ROOT / data).resolve()
        kwargs["provider"] = kwargs.get("provider", "builtin").lower()
        return cls(**kwargs)

    def prepare(self) -> None:
        for name in ("cache/api", "cache/llm", "logs", "runs", "reports", "bronze", "scheduler"):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)
