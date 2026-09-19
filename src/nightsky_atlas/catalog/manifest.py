"""Provenance manifests for processed catalogue data.

Processed data must remain traceable to raw sources and their license
(``AGENTS.md`` section 8.4).  Manifests are written deterministically so that a
repeated import produces an identical file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = ["file_sha256", "write_manifest"]


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> Path:
    """Write a manifest as sorted, indented JSON and return its path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target
