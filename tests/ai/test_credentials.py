"""Tests for .env credential loading."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nightsky_atlas.ai.credentials import load_env_file


def test_loads_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text(
        "# comment\nOPENROUTER_API_KEY=sk-test-123\nOTHER='quoted'\n", encoding="utf-8"
    )
    load_env_file(path)
    assert os.environ["OPENROUTER_API_KEY"] == "sk-test-123"
    assert os.environ["OTHER"] == "quoted"


def test_existing_env_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    path = tmp_path / ".env"
    path.write_text("OPENROUTER_API_KEY=from-file\n", encoding="utf-8")
    load_env_file(path)
    assert os.environ["OPENROUTER_API_KEY"] == "from-env"


def test_missing_file_is_ignored(tmp_path: Path) -> None:
    load_env_file(tmp_path / "does-not-exist")


def test_blank_lines_and_junk_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOT_A_PAIR", raising=False)
    path = tmp_path / ".env"
    path.write_text("\nNOT_A_PAIR\n=novalue\n", encoding="utf-8")
    load_env_file(path)
    assert "NOT_A_PAIR" not in os.environ