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
        "test-veil",
        "test-sparse",
        "test-orion",
        "test-pole",
    ]
    assert config.charts[0].projection == "stereographic"


def test_shipped_atlas_declares_visible_edition() -> None:
    config = load_atlas_config(ATLAS_FIXTURE)
    edition = config.resolved_edition()
    assert edition.name == "Standard"
    assert edition.code == "S"


def test_missing_edition_falls_back_to_registry(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "atlas.yaml", valid_atlas_dict())
    config = load_atlas_config(path)
    assert config.resolved_edition().name == "Standard"
    assert config.resolved_edition().code == "S"


def test_edition_rejects_blank_code(tmp_path: Path) -> None:
    data = valid_atlas_dict()
    data["edition"] = {"name": "Standard", "code": "  "}
    path = write_yaml(tmp_path / "atlas.yaml", data)
    with pytest.raises(ConfigError) as excinfo:
        load_atlas_config(path)
    assert "code" in str(excinfo.value)


def test_edition_rejects_unknown_key(tmp_path: Path) -> None:
    data = valid_atlas_dict()
    data["edition"] = {"name": "Standard", "code": "S", "colour": "blue"}
    path = write_yaml(tmp_path / "atlas.yaml", data)
    with pytest.raises(ConfigError) as excinfo:
        load_atlas_config(path)
    assert "colour" in str(excinfo.value)


def test_shipped_style_fixture_loads() -> None:
    config = load_style_config(STYLE_FIXTURE)
    assert config.id == "standard"
    assert config.star.min_diameter_mm == pytest.approx(0.36)
    assert config.star.label_magnitude_limit == pytest.approx(5.5)
    assert config.label.font_size_pt == pytest.approx(6.0)
    assert config.constellation.lines.enabled is True
    assert config.constellation.boundaries.enabled is True
    assert config.dso.outline_line_width_mm > 0.0
    assert config.dso.outline_dash_mm > 0.0


@pytest.mark.parametrize(
    "diameter_curve",
    (
        [[0.0, 1.0], [0.0, 0.8]],
        [[0.0, 0.8], [9.0, 1.0]],
        [[0.0, 1.0], [8.0, 0.4]],
    ),
)
def test_star_diameter_curve_is_strictly_validated(
    tmp_path: Path, diameter_curve: list[list[float]]
) -> None:
    data = valid_style_dict()
    data["star"]["diameter_curve"] = diameter_curve
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError) as excinfo:
        load_style_config(path)
    assert "diameter_curve" in str(excinfo.value)


def test_shipped_style_declares_subdued_furniture() -> None:
    config = load_style_config(STYLE_FIXTURE)
    furniture = config.furniture
    assert furniture.scale_bar.length_deg == pytest.approx(5.0)
    assert furniture.scale_bar.thickness_mm <= 0.2
    # Navigation is deliberately larger than the coordinate labels so it is
    # findable while flipping pages, but mid-grey and never bolder than sky
    # content.
    assert furniture.navigation.font_size_pt > config.grid.label_font_size_pt
    assert furniture.navigation.font_size_pt <= furniture.title_font_size_pt
    assert furniture.navigation.gray >= config.grid.label_gray
    assert not furniture.magnitude_legend.enabled


def test_magnitude_legend_rejects_manual_magnitudes(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["furniture"] = {"magnitude_legend": {"magnitudes": []}}
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError) as excinfo:
        load_style_config(path)
    assert "magnitudes" in str(excinfo.value)


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


def test_grid_label_step_must_align_with_line_step(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["grid"] = {"ra_step_deg": 2.0, "label_ra_step_deg": 3.0}
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError) as excinfo:
        load_style_config(path)
    assert "label_ra_step_deg" in str(excinfo.value)


def test_grid_label_step_multiple_is_valid(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["grid"] = {"ra_step_deg": 2.0, "label_ra_step_deg": 10.0}
    path = write_yaml(tmp_path / "style.yaml", data)
    config = load_style_config(path)
    assert config.grid.label_ra_step_deg == pytest.approx(10.0)
    assert config.grid.label_dec_step_deg is None


def test_shipped_atlas_declares_visibility_limits() -> None:
    config = load_atlas_config(ATLAS_FIXTURE)
    limits = config.visibility.to_limits()
    assert limits.integrated_magnitude_limit == pytest.approx(13.5)
    assert limits.surface_brightness_limit == pytest.approx(23.5)
    assert limits.min_axis_arcmin == pytest.approx(1.5)


def test_shipped_style_declares_dso_label_limit() -> None:
    config = load_style_config(STYLE_FIXTURE)
    assert config.label.dso_label_magnitude_limit == pytest.approx(12.5)


def test_shipped_style_declares_dso_label_hierarchy() -> None:
    config = load_style_config(STYLE_FIXTURE)
    labels = config.label.dso_labels
    assert labels.normal_size_pt == pytest.approx(6.5)
    assert labels.messier.size_factor == pytest.approx(1.15)
    assert labels.messier.weight == "bold"
    assert labels.herschel400.weight == "bold"
    assert labels.normal.weight == "normal"


def test_dso_label_invalid_weight_fails(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["label"]["dso_labels"] = {"messier": {"weight": "heavy"}}
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError) as excinfo:
        load_style_config(path)
    assert "weight" in str(excinfo.value)


def test_dso_label_regular_weight_alias(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["label"]["dso_labels"] = {"herschel400": {"weight": "regular"}}
    path = write_yaml(tmp_path / "style.yaml", data)
    config = load_style_config(path)
    assert config.label.dso_labels.herschel400.weight == "normal"


def test_dso_bold_line_width_must_not_be_thinner(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["dso"] = {"line_width_mm": 0.3, "bold_line_width_mm": 0.2}
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError):
        load_style_config(path)


def test_shipped_style_declares_bold_dso_stroke() -> None:
    config = load_style_config(STYLE_FIXTURE)
    assert config.dso.bold_line_width_mm > config.dso.line_width_mm


def test_shipped_style_declares_dso_extent_classes() -> None:
    config = load_style_config(STYLE_FIXTURE)
    assert config.dso.galaxy.use_angular_size is True
    assert config.dso.globular_cluster.use_angular_size is True
    assert config.dso.open_cluster.use_angular_size is True
    assert config.dso.planetary_nebula.use_angular_size is True
    assert (
        config.dso.globular_cluster.min_diameter_mm
        <= config.dso.globular_cluster.fallback_diameter_mm
    )


def test_dso_extent_min_above_fallback_fails(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["dso"] = {
        "globular_cluster": {
            "fallback_diameter_mm": 1.0,
            "min_diameter_mm": 2.0,
        }
    }
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError):
        load_style_config(path)


def test_dso_extent_max_below_min_fails(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["dso"] = {
        "open_cluster": {
            "fallback_diameter_mm": 2.0,
            "min_diameter_mm": 1.4,
            "max_diameter_mm": 1.0,
        }
    }
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError):
        load_style_config(path)


def test_dso_extent_unknown_key_fails(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["dso"] = {
        "globular_cluster": {
            "fallback_diameter_mm": 1.5,
            "min_diameter_mm": 1.2,
            "radius_mm": 1.0,
        }
    }
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError) as excinfo:
        load_style_config(path)
    assert "radius_mm" in str(excinfo.value)


def test_dso_label_unknown_key_fails(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["label"]["dso_labels"] = {"messier": {"font_size": 8.0}}
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError) as excinfo:
        load_style_config(path)
    assert "font_size" in str(excinfo.value)


def test_visibility_reference_outside_limit_fails(tmp_path: Path) -> None:
    data = valid_atlas_dict()
    data["visibility"] = {
        "integrated_magnitude_limit": 10.0,
        "reference_magnitude": 11.0,
    }
    path = write_yaml(tmp_path / "atlas.yaml", data)
    with pytest.raises(ConfigError):
        load_atlas_config(path)


def test_visibility_unknown_key_fails(tmp_path: Path) -> None:
    data = valid_atlas_dict()
    data["visibility"] = {"aperture_inches": 12.0}
    path = write_yaml(tmp_path / "atlas.yaml", data)
    with pytest.raises(ConfigError):
        load_atlas_config(path)


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


def test_shipped_style_declares_double_star_marker() -> None:
    config = load_style_config(STYLE_FIXTURE)
    assert config.double_stars.enabled is True
    assert config.double_stars.min_component_separation_mm == pytest.approx(0.7)
    assert config.double_stars.marker_length_factor == pytest.approx(1.8)
    assert config.double_stars.min_marker_length_mm == pytest.approx(0.8)
    assert config.double_stars.marker_line_width_mm == pytest.approx(0.15)
    assert config.double_stars.companion_magnitude_limit == pytest.approx(9.0)


def test_double_star_style_defaults_when_omitted(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "style.yaml", valid_style_dict())
    config = load_style_config(path)
    assert config.double_stars.enabled is True
    assert config.double_stars.min_component_separation_mm == pytest.approx(0.7)


def test_double_star_style_rejects_unknown_key(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["double_stars"] = {"min_component_separation_mm": 0.7, "colour": "red"}
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError):
        load_style_config(path)


def test_double_star_min_separation_must_be_positive(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["double_stars"] = {"min_component_separation_mm": 0.0}
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError):
        load_style_config(path)
