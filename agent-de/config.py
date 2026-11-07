"""Environment-backed configuration; importing does not read secrets or write files."""
from dataclasses import dataclass
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    """Runtime settings shared by CLI, UI, and tests."""

    data_dir: Path = ROOT / "data"
    provider: str = "ollama"
    gemini_key: str = ""
    groq_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
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

    @property
    def db_path(self) -> Path:
        """Return the persistent warehouse path."""
        return self.data_dir / "pipeline.duckdb"

    @classmethod
    def from_env(cls) -> "Settings":
        """Load the project .env, with existing environment variables taking precedence."""
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        data = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).expanduser()
        return cls(
            data_dir=(ROOT / data).resolve() if not data.is_absolute() else data.resolve(),
            provider=os.getenv("LLM_PROVIDER", "ollama").lower(),
            gemini_key=os.getenv("GEMINI_API_KEY", ""),
            groq_key=os.getenv("GROQ_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", cls.gemini_model),
            groq_model=os.getenv("GROQ_MODEL", cls.groq_model),
            ollama_model=os.getenv("OLLAMA_MODEL", cls.ollama_model),
            ollama_url=os.getenv("OLLAMA_URL", cls.ollama_url),
            api_cache_ttl=int(os.getenv("API_CACHE_TTL", "900")),
            llm_cache_ttl=int(os.getenv("LLM_CACHE_TTL", "86400")),
            http_timeout=float(os.getenv("HTTP_TIMEOUT", "20")),
            backoff_seconds=float(os.getenv("BACKOFF_SECONDS", "1")),
            sandbox_backend=os.getenv("SANDBOX_BACKEND", "auto"),
            sandbox_image=os.getenv("SANDBOX_IMAGE", cls.sandbox_image),
        )

    def prepare(self) -> None:
        """Create writable runtime directories."""
        for name in ("cache/api", "cache/llm", "logs", "runs", "reports"):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)
