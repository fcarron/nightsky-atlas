"""Credential loading.

Secrets are read from environment variables and never logged or committed
(``AGENTS.md`` section 33).  A git-ignored ``.env`` file is supported as a
convenience; real environment variables always take precedence.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["load_env_file"]

DEFAULT_ENV_FILE = Path(".env")


def load_env_file(path: str | Path = DEFAULT_ENV_FILE) -> None:
    """Load ``KEY=value`` pairs from a file into the environment.

    Existing environment variables are never overwritten.  Missing files are
    ignored.  Blank lines and lines starting with ``#`` are skipped.
    """
    resolved = Path(path)
    if not resolved.exists():
        return
    for line in resolved.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)