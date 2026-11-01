from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import BinaryIO

from task_control.config import get_settings

STDOUT_NAME = "stdout.log"
STDERR_NAME = "stderr.log"


def attempt_dir(run_id: str, attempt_no: int) -> Path:
    return Path(get_settings().output_root) / str(run_id) / str(attempt_no)


def ensure_attempt_dir(run_id: str, attempt_no: int) -> Path:
    path = attempt_dir(run_id, attempt_no)
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_tail(path: Path, max_bytes: int) -> tuple[str, int, bool]:
    """Read the last max_bytes of a file.

    Returns (text, total_bytes, truncated).
    """
    try:
        total = path.stat().st_size
    except OSError:
        return "", 0, False
    if max_bytes <= 0:
        return "", total, total > 0
    try:
        with path.open("rb") as handle:
            if total > max_bytes:
                handle.seek(total - max_bytes)
            data = handle.read()
    except OSError:
        return "", 0, False
    return data.decode("utf-8", errors="replace"), total, total > max_bytes


def tail_text(text: str, max_bytes: int) -> tuple[str, int, bool]:
    data = text.encode("utf-8")
    if max_bytes <= 0 or len(data) <= max_bytes:
        return text, len(data), False
    return data[-max_bytes:].decode("utf-8", errors="replace"), len(data), True


class RedactingCapture:
    """Pump a process pipe into a file while redacting known secret values.

    Output is capped to avoid unbounded disk usage. The stream is flushed on
    every chunk so another process (the API) can tail it while the task runs.
    """

    def __init__(self, path: Path, limit_bytes: int, secrets: tuple[str, ...]) -> None:
        self.path = path
        self.limit_bytes = max(limit_bytes, 1)
        self.secrets = tuple(secret for secret in secrets if secret)
        self.written = 0
        self.truncated = False
        self._handle = path.open("wb")
        self._lock = threading.Lock()

    def start(self, stream: BinaryIO) -> threading.Thread:
        thread = threading.Thread(target=self._pump, args=(stream,), daemon=True)
        thread.start()
        return thread

    def _pump(self, stream: BinaryIO) -> None:
        try:
            while True:
                chunk = stream.read1(65536) if hasattr(stream, "read1") else stream.read(65536)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                for secret in self.secrets:
                    text = text.replace(secret, "***")
                data = text.encode("utf-8")
                with self._lock:
                    if self.written >= self.limit_bytes:
                        self.truncated = True
                        continue
                    remaining = self.limit_bytes - self.written
                    if len(data) > remaining:
                        data = data[:remaining]
                        self.truncated = True
                    self._handle.write(data)
                    self._handle.flush()
                    self.written += len(data)
        finally:
            with self._lock:
                if not self._handle.closed:
                    self._handle.flush()
                    self._handle.close()

    def close(self) -> None:
        with self._lock:
            if not self._handle.closed:
                self._handle.flush()
                self._handle.close()


def cleanup_run_output(run_id: str) -> None:
    shutil.rmtree(Path(get_settings().output_root) / str(run_id), ignore_errors=True)


def cleanup_output_root(cutoff_seconds: float) -> int:
    """Remove per-run output directories older than the cutoff."""
    root = Path(get_settings().output_root)
    if not root.exists():
        return 0
    removed = 0
    for entry in root.iterdir():
        try:
            if not entry.is_dir():
                continue
            age = time.time() - entry.stat().st_mtime
            if age >= cutoff_seconds:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed
