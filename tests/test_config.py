"""Tests for strict typed configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from nightsky_atlas.atlas.config import (
    ConfigError,
    load_atlas_config,
    load_style_config,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ATLAS_FIXTURE = REPO_ROOT / "atlas" / "standard.yaml"
STYLE_FIXTURE = REPO_ROOT / "styles" / "standard.yaml"


def write_yaml(path: Path, data: Any) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def valid_atlas_dict() -> dict[str, Any]:
    return {
        "id": "standard",
        "page": {"width_mm": 297.0, "height_mm": 210.0, "margin_mm": 12.0},
        "charts": [
            {
                "id": "test-virgo",
                "center_ra_deg": 187.5,
                "center_dec_deg": 12.0,
                "width_deg": 20.0,
                "height_deg": 14.0,
            }
        ],
    }


def valid_style_dict() -> dict[str, Any]:
    return {
        "id": "standard",
        "star": {
            "min_diameter_mm": 0.2,
            "max_diameter_mm": 1.6,
            "bright_magnitude": 0.0,
            "faint_magnitude": 10.0,
        },
        "label": {"font_family": "DejaVu Sans", "font_size_pt": 6.0},
    }


def test_shipped_atlas_fixture_loads() -> None:
    config = load_atlas_config(ATLAS_FIXTURE)
    assert config.id == "standard"
    assert config.page.width_mm == pytest.approx(297.0)
    assert config.page.margin_mm == pytest.approx(12.0)
    assert config.stellar_limit_magnitude == pytest.approx(9.0)
    assert [chart.id for chart in config.charts] == [
        "test-virgo",
        "test-cygnus",
        "test-sparse",
    ]
    assert config.charts[0].projection == "stereographic"


def test_shipped_style_fixture_loads() -> None:
    config = load_style_config(STYLE_FIXTURE)
    assert config.id == "standard"
    assert config.star.min_diameter_mm == pytest.approx(0.2)
    assert config.label.font_size_pt == pytest.approx(6.0)


def test_valid_dict_loads(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "atlas.yaml", valid_atlas_dict())
    config = load_atlas_config(path)
    assert config.charts[0].rotation_deg == pytest.approx(0.0)


def test_unknown_top_level_key_fails(tmp_path: Path) -> None:
    data = valid_atlas_dict()
    data["tiling"] = {"strategy": "bands"}
    path = write_yaml(tmp_path / "atlas.yaml", data)
    with pytest.raises(ConfigError) as excinfo:
        load_atlas_config(path)
    assert "tiling" in str(excinfo.value)


def test_unknown_nested_key_fails(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["star"]["colour"] = "red"
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError) as excinfo:
        load_style_config(path)
    assert "colour" in str(excinfo.value)


def test_missing_required_key_fails(tmp_path: Path) -> None:
    data = valid_atlas_dict()
    del data["page"]["height_mm"]
    path = write_yaml(tmp_path / "atlas.yaml", data)
    with pytest.raises(ConfigError) as excinfo:
        load_atlas_config(path)
    assert "height_mm" in str(excinfo.value)


def test_negative_page_dimension_fails(tmp_path: Path) -> None:
    data = valid_atlas_dict()
    data["page"]["width_mm"] = -297.0
    path = write_yaml(tmp_path / "atlas.yaml", data)
    with pytest.raises(ConfigError):
        load_atlas_config(path)


def test_unknown_projection_fails(tmp_path: Path) -> None:
    data = valid_atlas_dict()
    data["charts"][0]["projection"] = "mercator"
    path = write_yaml(tmp_path / "atlas.yaml", data)
    with pytest.raises(ConfigError):
        load_atlas_config(path)


def test_max_diameter_below_min_fails(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["star"]["max_diameter_mm"] = 0.1
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError):
        load_style_config(path)


def test_missing_file_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_atlas_config(tmp_path / "does-not-exist.yaml")


def test_empty_file_fails(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_atlas_config(path)


def test_non_mapping_root_fails(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_atlas_config(path)
