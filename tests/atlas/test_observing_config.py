"""Tests for observing-list selection configuration and inheritance."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import ConfigError
from nightsky_atlas.atlas.observing_config import (
    load_observing_lists_config,
    resolve_edition,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED = REPO_ROOT / "config" / "observing_lists.yaml"


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "observing_lists.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_shipped_config_and_resolve_standard() -> None:
    config = load_observing_lists_config(SHIPPED)
    assert "herschel400" in config.lists
    policy = resolve_edition(config, "standard")
    assert policy.forced_lists == frozenset({"herschel400"})
    assert dict(policy.list_weights)["messier"] == 60
    assert dict(policy.list_weights)["herschel400"] == 50


def test_deep_inherits_standard() -> None:
    config = load_observing_lists_config(SHIPPED)
    policy = resolve_edition(config, "deep")
    assert {"herschel400", "herschel2", "planetary_nebula_al"} <= policy.forced_lists
    weights = dict(policy.list_weights)
    assert weights["messier"] == 60
    assert weights["hickson"] == 20


def test_unknown_edition_selects_nothing() -> None:
    config = load_observing_lists_config(SHIPPED)
    policy = resolve_edition(config, "not-an-edition")
    assert policy.forced_lists == frozenset()
    assert policy.list_weights == ()


def test_missing_config_is_empty() -> None:
    config = load_observing_lists_config(Path("does-not-exist.yaml"))
    assert config.editions == {}
    assert resolve_edition(config, "standard").forced_lists == frozenset()


def test_unknown_key_fails(tmp_path: Path) -> None:
    path = write_config(tmp_path, "editions:\n  standard:\n    bogus: 1\n")
    with pytest.raises(ConfigError):
        load_observing_lists_config(path)


def test_negative_weight_fails(tmp_path: Path) -> None:
    path = write_config(
        tmp_path, "editions:\n  standard:\n    list_weights:\n      messier: -1\n"
    )
    with pytest.raises(ConfigError):
        load_observing_lists_config(path)


def test_edition_referencing_unknown_list_fails(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        "lists:\n  messier:\n    name: Messier\n"
        "editions:\n  standard:\n    forced_lists:\n      - nope\n",
    )
    with pytest.raises(ConfigError, match="unknown"):
        load_observing_lists_config(path)


def test_inheritance_cycle_fails(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        "editions:\n  a:\n    inherit: b\n  b:\n    inherit: a\n",
    )
    config = load_observing_lists_config(path)
    with pytest.raises(ConfigError, match="cycle"):
        resolve_edition(config, "a")


def test_missing_inherited_edition_fails(tmp_path: Path) -> None:
    path = write_config(tmp_path, "editions:\n  a:\n    inherit: nope\n")
    config = load_observing_lists_config(path)
    with pytest.raises(ConfigError, match="unknown edition"):
        resolve_edition(config, "a")
