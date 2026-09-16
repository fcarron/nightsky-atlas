"""Tests for AI configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from nightsky_atlas.ai.config import AIConfigError, load_ai_config


def write_config(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "ai.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def valid_config() -> dict:
    return {"reviewer_model": "test/model", "enabled": False}


def test_load_valid_config(tmp_path: Path) -> None:
    config = load_ai_config(write_config(tmp_path, valid_config()))
    assert config.reviewer_model == "test/model"
    assert config.provider == "openrouter"
    assert config.max_iterations == 4


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(AIConfigError):
        load_ai_config(tmp_path / "missing.yaml")


def test_unknown_key_fails(tmp_path: Path) -> None:
    data = valid_config()
    data["temperature"] = 0.5
    with pytest.raises(AIConfigError):
        load_ai_config(write_config(tmp_path, data))


def test_blank_model_fails(tmp_path: Path) -> None:
    data = valid_config()
    data["reviewer_model"] = "   "
    with pytest.raises(AIConfigError):
        load_ai_config(write_config(tmp_path, data))


def test_unknown_provider_fails(tmp_path: Path) -> None:
    data = valid_config()
    data["provider"] = "anthropic"
    with pytest.raises(AIConfigError):
        load_ai_config(write_config(tmp_path, data))