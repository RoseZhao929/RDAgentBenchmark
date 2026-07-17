"""Append-only JSONL prediction logger.

Thread-safe(ish) — uses one file handle per logger instance and writes whole
JSON lines atomically per call.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Optional

from harness.logging.schema import PredictionLog

_LOCK = threading.Lock()


class JsonlPredictionLogger:
    """Writer for prediction logs.

    Usage:
        logger = JsonlPredictionLogger("/path/to/run_xyz/predictions.jsonl")
        log = PredictionLog(...)
        logger.write(log)
    """

    def __init__(self, path: str | Path, autoflush: bool = True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("a", buffering=1 if autoflush else -1)

    def write(self, log: PredictionLog) -> None:
        line = log.model_dump_json() + "\n"
        with _LOCK:
            self._f.write(line)
            if hasattr(self._f, "flush"):
                self._f.flush()
                os.fsync(self._f.fileno())

    def close(self) -> None:
        with _LOCK:
            try:
                self._f.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def read_logs(path: str | Path) -> list[PredictionLog]:
    """Read all log entries from a JSONL file (sorted by line order)."""
    out: list[PredictionLog] = []
    p = Path(path)
    if not p.exists():
        return out
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(PredictionLog.model_validate_json(line))
    return out


__all__ = ["JsonlPredictionLogger", "read_logs"]
