"""Observe bounded private host trees; this is a kill trigger, not a filesystem quota."""

from __future__ import annotations

import os
import signal
import threading
from pathlib import Path
from typing import Any


def tree_usage(root: Path, *, max_bytes: int, max_entries: int) -> tuple[int, int]:
    total = entries = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as items:
                for item in items:
                    try:
                        info = item.stat(follow_symlinks=False)
                        entries += 1
                        total += info.st_size
                        if total > max_bytes or entries > max_entries:
                            return total, entries
                        if item.is_dir(follow_symlinks=False):
                            pending.append(Path(item.path))
                    except FileNotFoundError:
                        continue
        except FileNotFoundError:
            continue
    return total, entries


class HostTreeMonitor:
    """Terminate only an owned, unreaped broker when its tree exceeds admission."""

    def __init__(self, root: Path, process: Any, *, max_bytes: int = 128 * 1024**2,
                 max_entries: int = 10_000) -> None:
        self.root, self.process = root, process
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.reason: str | None = None
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self.done.is_set():
            try:
                size, entries = tree_usage(self.root, max_bytes=self.max_bytes,
                                          max_entries=self.max_entries)
                if size > self.max_bytes or entries > self.max_entries:
                    self.reason = f"private tree exceeded bound: bytes={size}, entries={entries}"
            except OSError as exc:
                self.reason = "private tree cannot be audited: " + type(exc).__name__
            if self.reason:
                if self.process.poll() is None:
                    try:
                        os.killpg(self.process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                return
            self.done.wait(0.1)

    def stop(self) -> None:
        self.done.set()
        self.thread.join(timeout=2)
