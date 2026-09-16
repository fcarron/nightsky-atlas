"""Smoke tests for the executable skeleton."""

from __future__ import annotations

import subprocess
import sys

import pytest

from nightsky_atlas import __version__
from nightsky_atlas.cli import main


def test_version_is_string() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_main_with_no_args_returns_zero() -> None:
    assert main([]) == 0


def test_main_help_returns_zero() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0


def test_module_help_via_subprocess() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "nightsky_atlas", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()
