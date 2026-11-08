"""Atomic, expiring JSON cache keyed by canonical request hashes."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any


def digest(value: Any) -> str:
    """Hash a JSON-serializable request deterministically."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class DiskCache:
    """Cache only successfully decoded results; tolerate corrupt cache entries."""

    def __init__(self, directory: Path, ttl: int):
        self.directory, self.ttl = directory, ttl
        directory.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> Any | None:
        """Return a fresh entry, or None when absent, expired, or corrupt."""
        try:
            item = json.loads((self.directory / f"{key}.json").read_text())
            if time.time() - item["created"] < self.ttl:
                return item["value"]
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        return None

    def put(self, key: str, value: Any) -> None:
        """Replace an entry atomically, including under concurrent readers."""
        fd, filename = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({"created": time.time(), "value": value}, stream)
            os.replace(filename, self.directory / f"{key}.json")
        finally:
            Path(filename).unlink(missing_ok=True)
