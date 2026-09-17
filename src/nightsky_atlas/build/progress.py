"""Progress reporting for long-running atlas builds.

``Progress`` writes timestamped status lines to a stream so an interactive
build and a captured log both explain where the time goes.  Two levels are
available: :meth:`info` for normal progress and :meth:`detail` (only emitted in
verbose mode) for per-stage timings.  :meth:`step` is a context manager that
measures a block and reports its elapsed time at the active level.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TextIO

__all__ = ["Progress"]


class Progress:
    """Timestamped, optionally verbose build progress reporter."""

    def __init__(
        self,
        *,
        verbose: bool = False,
        enabled: bool = True,
        stream: TextIO | None = None,
    ) -> None:
        self.verbose = verbose
        self.enabled = enabled
        self.stream = stream if stream is not None else sys.stderr
        self._start = time.perf_counter()

    @property
    def elapsed_s(self) -> float:
        """Seconds since this reporter was created."""
        return time.perf_counter() - self._start

    def _emit(self, message: str) -> None:
        print(f"[{self.elapsed_s:7.1f}s] {message}", file=self.stream, flush=True)

    def info(self, message: str) -> None:
        """Emit a normal progress line."""
        if self.enabled:
            self._emit(message)

    def detail(self, message: str) -> None:
        """Emit an indented line, only in verbose mode."""
        if self.enabled and self.verbose:
            self._emit(f"    {message}")

    @contextmanager
    def step(self, message: str, *, detail: bool = False) -> Iterator[None]:
        """Measure and report the elapsed time of a block.

        ``detail=True`` emits the timing only in verbose mode; otherwise it is
        emitted at normal level.
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            if detail:
                self.detail(f"{message}: {elapsed:.2f}s")
            else:
                self.info(f"{message}: {elapsed:.2f}s")


def null_progress() -> Progress:
    """Return a disabled reporter for callers without one."""
    return Progress(enabled=False)
