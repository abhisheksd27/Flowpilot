"""Structured run events, bounded summaries, and atomic JSON result files."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Callable
from tools.cache import DiskCache

logger = logging.getLogger("flowpilot")


def write_json(path: Path, value: dict) -> None:
    """Atomically replace a complete JSON document."""
    import os
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, default=str, allow_nan=False, indent=2)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class EventLog:
    """Publish observable operations, never hidden model reasoning or credentials."""
    def __init__(self, path: Path, run_id: str, callback: Callable | None = None):
        self.path, self.run_id, self.callback = path, run_id, callback
        self.events = []
        self.retry_count = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, node: str, status: str, message: str, *, tool: str = "", args=None,
             result=None, error: str | None = None, duration: float = 0, outcome=None, metrics=None):
        event = {"timestamp": datetime.now(timezone.utc).isoformat(), "run_id": self.run_id,
                 "node": node, "status": status, "message": message, "thought_summary": message,
                 "tool": tool or node, "args": args or {}, "result": result,
                 "error": error, "retry_count": self.retry_count, "duration": round(duration, 4),
                 "outcome": outcome, "metrics": metrics or {}}
        self.events.append(event)
        with self.path.open("a") as stream:
            stream.write(json.dumps(event, default=str, allow_nan=False) + "\n")
        logger.info("%s %s: %s", node, status, message)
        if self.callback:
            self.callback(event)
        return event

    @contextmanager
    def operation(self, node: str, message: str, *, args=None):
        started = time.monotonic()
        self.emit(node, "running", message, args=args)
        try:
            yield
        except Exception as error:
            self.emit(node, "failed", str(error)[:2000], error=str(error)[:4000], duration=time.monotonic()-started)
            raise
        else:
            self.emit(node, "success", message, duration=time.monotonic()-started)
